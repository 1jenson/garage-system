# Round 19 screenshots

Demo-data screenshots of the Workshop mock after round 19 (desktop layouts, customers, diary booking forms, tyres, quote/invoice editor, payments, ring-backs, notes, suppliers).

`shots.mjs` is a copy of `../shots.mjs` with the round-19 shot list (2x at 1440px, 3x at 375px). Run:

```bash
cd mock && python3 -m http.server 8793 &
node tools/screens/round-19/shots.mjs tools/screens/round-19 /tmp/shots-profile [name-prefix]
```

Use a fresh profile dir each run: a profile that once held another app's service worker can serve the wrong page. The optional third argument re-captures only shots whose name starts with it.
