> **Sample report** — generated from synthetic data so you can see the format. Not a real site, not a real run.

# crowd-test report — https://demo-shop.example (sample data)

*Generated (sample) by [crowd-test](https://github.com/anhhuyn411-alt/crowd-test)*

## Verdict

**🏆 Survival grade: F (38/100)** — ☠️ the mob destroyed it

- **Virtual users:** 3 sent, 3 completed
- **Average satisfaction:** 4.7/10
- **Findings:** 2 critical / 1 major / 2 minor

## Findings

- 🔴 **[critical/ux] Checkout forces account creation before showing total price** ✅ *verified by detective* — No guest checkout; the full cost is hidden until after email verification. Cart abandoned at step 2 of 5. _(found by Mai — The Impatient Shopper, at: Checkout step 2)_ — detective: Reproduced on a clean load: guest path does not exist.
- 🔴 **[critical/bug] Raw 500 error page when address contains emoji** ✅ *verified by detective* — Address field accepts any input, but the shipping calculator crashes server-side and shows an unstyled stack trace. _(found by Rex — The Chaos Monkey, at: Checkout shipping step)_ — detective: Reproduced: same 500 with a minimal emoji payload.
- 🟠 **[major/accessibility] Header icons carry no text labels** ✅ *verified by detective* — Menu, search, and cart are icon-only. For users who don't know the conventions, the site's entire navigation is invisible. _(found by Harold — The Senior Citizen, at: Site header)_ — detective: Confirmed: no visible labels and no aria-labels on 2 of 3 header icons.
- 🟠 **[major/bug] Browser back during payment silently empties the cart** ⚠️ *could not be reproduced — excluded from grade* — Going back from payment to cart loses all items with no warning; user must rebuild the cart from scratch. _(found by Rex — The Chaos Monkey, at: Payment page → back)_ — detective: Could not reproduce on a clean run — cart survived the back navigation twice.
- 🟡 **[minor/performance] Product images load noticeably late on the listing grid** —  _(found by Mai — The Impatient Shopper, at: Category page)_
- 🟡 **[minor/ux] Success message disappears after 2 seconds** — The 'added to cart' toast vanishes before a slow reader finishes reading it. _(found by Harold — The Senior Citizen, at: Product page)_

## The crowd

### Mai — The Impatient Shopper — 3/10, gave up on their goal

> Found a jacket I actually liked in about ten seconds — great start. Then checkout demanded I create an account, verify my email, AND hand over my phone number before showing shipping costs. I have meetings. I left the jacket behind.

### Harold — The Senior Citizen — 6/10, achieved their goal

> A patient afternoon got me there in the end. But I nearly gave up at the start: the little picture buttons at the top have no words, and I sat wondering what a stack of three lines could possibly mean.

### Rex — The Chaos Monkey — 5/10, achieved their goal

> Emoji in the address field? Accepted, then exploded at the shipping step with a raw 500 page. Back button during payment? Cart emptied itself. This site fears me, as it should.
