"""Promises made to hardware partners must survive every rewrite.

Source of truth: docs/partners/partners.json. See docs/partners/COMMITMENTS.md.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARTNERS = json.loads((ROOT / 'docs' / 'partners' / 'partners.json').read_text(encoding='utf8'))['partners']


def read(rel):
    return (ROOT / rel).read_text(encoding='utf8')


class PartnerCommitments(unittest.TestCase):
    def test_partner_pages_exist(self):
        for p in PARTNERS:
            self.assertTrue((ROOT / p['page']).is_file(), p['page'])

    def test_partner_credited_with_link(self):
        for p in PARTNERS:
            for rel in p.get('credit_required_in', []):
                with self.subTest(partner=p['id'], file=rel):
                    self.assertTrue(p['url'].split('://', 1)[1].removeprefix('www.') in read(rel),
                                  f"{p['name']} credit (link to {p['url']}) missing from {rel}")

    def test_product_links_kept(self):
        for p in PARTNERS:
            urls = [x['url'] for x in p['products'] if x.get('url')]
            for rel in p.get('product_link_required_in', []):
                text = read(rel)
                for url in urls:
                    with self.subTest(partner=p['id'], file=rel, url=url):
                        self.assertTrue(url in text, f"{p['name']} product link missing from {rel}")

    def test_promised_deliverables_exist(self):
        for p in PARTNERS:
            for d in p.get('deliverables', []):
                with self.subTest(partner=p['id'], deliverable=d['id']):
                    self.assertTrue((ROOT / d['file']).is_file(), d['file'])

    def test_media_permission_recorded_on_partner_page(self):
        for p in PARTNERS:
            if p.get('media_permission', {}).get('granted'):
                self.assertTrue('Media authorization' in read(p['page']), p['page'])

    def test_readme_partner_section_lists_every_partner(self):
        readme = read('README.md')
        self.assertTrue('<!-- partners:start' in readme and '<!-- partners:end -->' in readme,
                        'README partner strip markers (<!-- partners:start ... --> / <!-- partners:end -->) are missing')
        section = readme.split('<!-- partners:start', 1)[1].split('<!-- partners:end -->', 1)[0]
        for p in PARTNERS:
            self.assertTrue(p['name'] in section, f"{p['name']} missing from the README partner strip")


if __name__ == '__main__':
    unittest.main()
