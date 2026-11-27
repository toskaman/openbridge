// OpenBridge Companion: AI on the phone (libobai.so).
// A small language model (llama.cpp) and speech-to-text (whisper.cpp), on the phone's CPU, behind a tiny JNI surface
// used by fr.openbridge.companion.LocalAi. Nothing here touches the network.
#include <jni.h>
#include <android/log.h>

#include <cstring>
#include <mutex>
#include <string>
#include <vector>

#include "llama.h"
#include "whisper.h"

#define TAG "obai"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

namespace {

struct Llm {
    llama_model * model = nullptr;
    llama_context * ctx = nullptr;
    llama_sampler * smpl = nullptr;
    llama_batch_ext * batch = nullptr;
    std::mutex mu;
};

std::once_flag g_backend;

std::string jstr(JNIEnv * env, jstring s) {
    if (!s) return {};
    const char * c = env->GetStringUTFChars(s, nullptr);
    std::string out(c ? c : "");
    if (c) env->ReleaseStringUTFChars(s, c);
    return out;
}

// JNI's NewStringUTF wants modified UTF-8 and aborts on invalid bytes: keep only complete UTF-8 sequences.
jstring safe_utf8(JNIEnv * env, const std::string & s) {
    std::string out;
    out.reserve(s.size());
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = (unsigned char) s[i];
        size_t n = c < 0x80 ? 1 : (c >> 5) == 0x6 ? 2 : (c >> 4) == 0xE ? 3 : (c >> 3) == 0x1E ? 4 : 0;
        if (n == 0 || i + n > s.size()) { i++; continue; }
        bool ok = true;
        for (size_t k = 1; k < n; k++) if ((((unsigned char) s[i + k]) >> 6) != 0x2) { ok = false; break; }
        if (ok && n < 4 && c != 0) out.append(s, i, n);      // 4-byte (emoji) dropped: the glasses can't show them anyway
        i += ok ? n : 1;
    }
    return env->NewStringUTF(out.c_str());
}

void quiet_log(enum ggml_log_level level, const char * text, void *) {
    if (level == GGML_LOG_LEVEL_ERROR) __android_log_print(ANDROID_LOG_ERROR, TAG, "%s", text);   // not CONT (progress dots)
}

void set_tokens(llama_batch_ext * batch, const llama_token * tokens, int32_t n, llama_pos pos0) {
    llama_batch_ext_clear(batch);
    for (int32_t i = 0; i < n; ++i) {
        const int32_t idx = llama_batch_ext_add_token(batch, 0, tokens[i]);
        const llama_pos pos = pos0 + i;
        llama_batch_ext_set_pos(batch, idx, &pos);
    }
    llama_batch_ext_set_output_logits(batch, n - 1, true);
}

}  // namespace

extern "C" {

JNIEXPORT jstring JNICALL Java_fr_openbridge_companion_LocalAi_info(JNIEnv * env, jclass) {
    std::string s = std::string("llama.cpp + whisper.cpp, CPU");
    const char * sys = llama_print_system_info();
    if (sys && strstr(sys, "DOTPROD = 1")) s += ", dotprod";
    if (sys && strstr(sys, "FP16_VA = 1")) s += ", fp16";
    return env->NewStringUTF(s.c_str());
}

JNIEXPORT jlong JNICALL Java_fr_openbridge_companion_LocalAi_llmInit(JNIEnv * env, jclass, jstring path, jint n_ctx, jint threads) {
    std::call_once(g_backend, [] { llama_log_set(quiet_log, nullptr); whisper_log_set(quiet_log, nullptr); llama_backend_init(); });
    std::string p = jstr(env, path);
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 0;
    auto * h = new Llm();
    h->model = llama_model_load_from_file(p.c_str(), mp);
    if (!h->model) { LOGE("cannot load %s", p.c_str()); delete h; return 0; }
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = n_ctx > 0 ? n_ctx : 1024;
    cp.n_batch = cp.n_ctx;
    cp.n_threads = threads;
    cp.n_threads_batch = threads;
    h->ctx = llama_init_from_model(h->model, cp);
    if (!h->ctx) { llama_model_free(h->model); delete h; return 0; }
    h->smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(h->smpl, llama_sampler_init_top_k(40));
    llama_sampler_chain_add(h->smpl, llama_sampler_init_min_p(0.05f, 1));
    llama_sampler_chain_add(h->smpl, llama_sampler_init_temp(0.3f));
    llama_sampler_chain_add(h->smpl, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));
    h->batch = llama_batch_ext_init(h->ctx);
    return reinterpret_cast<jlong>(h);
}

// One question, one short answer: the context starts empty each time (no history kept on the phone).
JNIEXPORT jstring JNICALL Java_fr_openbridge_companion_LocalAi_llmChat(JNIEnv * env, jclass, jlong handle, jstring jsys, jstring juser, jint max_tokens) {
    auto * h = reinterpret_cast<Llm *>(handle);
    if (!h) return nullptr;
    std::lock_guard<std::mutex> lock(h->mu);
    std::string sys = jstr(env, jsys), user = jstr(env, juser);
    const llama_vocab * vocab = llama_model_get_vocab(h->model);
    llama_memory_clear(llama_get_memory(h->ctx), true);
    llama_sampler_reset(h->smpl);

    std::vector<llama_chat_message> msgs;
    if (!sys.empty()) msgs.push_back({"system", sys.c_str()});
    msgs.push_back({"user", user.c_str()});
    const char * tmpl = llama_model_chat_template(h->model, nullptr);
    std::vector<char> buf(4096);
    int n = llama_chat_apply_template(tmpl, msgs.data(), msgs.size(), true, buf.data(), buf.size());
    if (n > (int) buf.size()) { buf.resize(n); n = llama_chat_apply_template(tmpl, msgs.data(), msgs.size(), true, buf.data(), buf.size()); }
    std::string prompt = n > 0 ? std::string(buf.data(), n) : sys + "\n\n" + user + "\n";
    // Qwen3 / 3.5 chat format: an empty reasoning block asks for a direct answer (no "thinking" tokens on a phone).
    const std::string asst = "<|im_start|>assistant\n";
    if (prompt.size() >= asst.size() && prompt.compare(prompt.size() - asst.size(), asst.size(), asst) == 0)
        prompt += "<think>\n\n</think>\n\n";

    const int n_prompt = -llama_tokenize(vocab, prompt.c_str(), prompt.size(), nullptr, 0, true, true);
    std::vector<llama_token> toks(n_prompt);
    if (llama_tokenize(vocab, prompt.c_str(), prompt.size(), toks.data(), toks.size(), true, true) < 0) return nullptr;
    const int n_ctx = llama_n_ctx(h->ctx);
    if ((int) toks.size() > n_ctx - 8) toks.erase(toks.begin(), toks.end() - (n_ctx - 8));   // keep the end of a long prompt

    std::string out;
    const llama_token * cur = toks.data();
    int n_cur = toks.size();
    llama_pos pos = 0;
    llama_token tok;
    for (int i = 0; i < max_tokens; i++) {
        if (pos + n_cur > n_ctx) break;
        set_tokens(h->batch, cur, n_cur, pos);
        if (llama_process(h->ctx, LLAMA_PROCESS_TYPE_DECODE, h->batch) != 0) break;
        pos += n_cur;
        tok = llama_sampler_sample(h->smpl, h->ctx, -1);
        if (llama_vocab_is_eog(vocab, tok)) break;
        char piece[256];
        int k = llama_token_to_piece(vocab, tok, piece, sizeof(piece), 0, false);
        if (k > 0) out.append(piece, k);
        cur = &tok;
        n_cur = 1;
    }
    return safe_utf8(env, out);
}

JNIEXPORT void JNICALL Java_fr_openbridge_companion_LocalAi_llmFree(JNIEnv *, jclass, jlong handle) {
    auto * h = reinterpret_cast<Llm *>(handle);
    if (!h) return;
    if (h->batch) llama_batch_ext_free(h->batch);
    if (h->smpl) llama_sampler_free(h->smpl);
    if (h->ctx) llama_free(h->ctx);
    if (h->model) llama_model_free(h->model);
    delete h;
}

JNIEXPORT jlong JNICALL Java_fr_openbridge_companion_LocalAi_sttInit(JNIEnv * env, jclass, jstring path) {
    std::call_once(g_backend, [] { llama_log_set(quiet_log, nullptr); whisper_log_set(quiet_log, nullptr); llama_backend_init(); });
    std::string p = jstr(env, path);
    whisper_context_params cp = whisper_context_default_params();
    cp.use_gpu = false;
    whisper_context * ctx = whisper_init_from_file_with_params(p.c_str(), cp);
    if (!ctx) LOGE("cannot load %s", p.c_str());
    return reinterpret_cast<jlong>(ctx);
}

JNIEXPORT jstring JNICALL Java_fr_openbridge_companion_LocalAi_sttRun(JNIEnv * env, jclass, jlong handle, jfloatArray pcm, jstring jlang, jint threads) {
    auto * ctx = reinterpret_cast<whisper_context *>(handle);
    if (!ctx || !pcm) return nullptr;
    std::string lang = jstr(env, jlang);
    jsize n = env->GetArrayLength(pcm);
    std::vector<float> samples(n);
    env->GetFloatArrayRegion(pcm, 0, n, samples.data());
    whisper_full_params fp = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    fp.n_threads = threads;
    fp.language = lang.empty() ? "auto" : lang.c_str();
    fp.translate = false;
    fp.no_context = true;
    fp.no_timestamps = true;
    fp.single_segment = true;
    fp.print_progress = false;
    fp.print_realtime = false;
    fp.print_timestamps = false;
    fp.print_special = false;
    fp.suppress_blank = true;
    if (whisper_full(ctx, fp, samples.data(), n) != 0) return nullptr;
    std::string out;
    for (int i = 0; i < whisper_full_n_segments(ctx); i++) out += whisper_full_get_segment_text(ctx, i);
    return safe_utf8(env, out);
}

JNIEXPORT void JNICALL Java_fr_openbridge_companion_LocalAi_sttFree(JNIEnv *, jclass, jlong handle) {
    auto * ctx = reinterpret_cast<whisper_context *>(handle);
    if (ctx) whisper_free(ctx);
}

}  // extern "C"
