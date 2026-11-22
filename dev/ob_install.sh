F=${1:-ActiveLook-OpenBridge-NoSplit-v3.apk}
ID=$(content query --uri content://media/external/file --projection _id --where "_display_name='$F'" | sed -n 's/.*_id=\([0-9]*\).*/\1/p' | head -1)
echo "media id: $ID"
if [ -z "$ID" ]; then am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/$F >/dev/null; sleep 2
  ID=$(content query --uri content://media/external/file --projection _id --where "_display_name='$F'" | sed -n 's/.*_id=\([0-9]*\).*/\1/p' | head -1); echo "media id after scan: $ID"; fi
am start -a android.intent.action.VIEW -t application/vnd.android.package-archive -d content://media/external/file/$ID -n com.google.android.packageinstaller/com.android.packageinstaller.InstallStart --grant-read-uri-permission
sleep 4
dumpsys window | grep mCurrentFocus | head -1
screencap -p /sdcard/ob_screen.png
