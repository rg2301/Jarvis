# test_search.py
import sys, os, logging, html
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

for mod in list(sys.modules.keys()):
    if 'jarvis' in mod:
        del sys.modules[mod]

from jarvis import WebBrain
logging.basicConfig(level=logging.INFO)
web = WebBrain()

print("\n=== News Search ===")
results = web.search_news("IPL 2025")
for r in results[:3]:
    print(f"  Title:  {r['title']}")
    print(f"  Desc:   {r['description'][:100]}")
    print()

print("\n=== Bitcoin Price ===")
results = web.get_price("Bitcoin")
for r in results[:2]:
    print(f"  {r['title']}: {r['description']}")

print("\n=== Ethereum Price ===")
results = web.get_price("Ethereum")
for r in results[:2]:
    print(f"  {r['title']}: {r['description']}")

print("\n=== General Search ===")
results = web.search("Anthropic Claude AI")
for r in results[:2]:
    print(f"  Title: {r['title']}")
    print(f"  Desc:  {r['description'][:100]}")
    print()