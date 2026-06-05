# Product

## Register

product

## Users

Sales / BD operators doing technical outreach inside the network-operator world.
They work with ASNs, ARIN-managed role emails (abuse / technical / administrative /
routing / NOC), and peering contacts at ISPs, CDNs, datacenters, and cloud networks.
Their day: run ASN lookups, fire AI-assisted lead discovery across multiple search
sources, import the good rows (with block/allow filtering), set follow-up status,
send templated outreach via mailto, and watch the pipeline in stats. They sit at a
desk in daylight, scanning dense tables and forms, often for long stretches. The UI
is Chinese-first.

## Product Purpose

An internal Sales CRM that converts network-infrastructure data into a managed,
actionable contact pipeline: lookup or AI-discover, then import, filter, track,
template-email, and measure. It exists to make finding and working network-operator
contacts fast and trustworthy. Success looks like: a clean lookup-to-import flow,
contacts that are easy to triage and act on, and zero moments where the operator
distrusts what they see.

## Brand Personality

Precise, restrained, trustworthy. An instrument, not a toy. The voice is direct and
technical without being cold; confident because it is accurate. Three words: precise,
restrained, engineered. Emotional goal: the operator feels they are driving a sharp
professional tool and stay in control of dense data.

## Anti-references

The generic blue-and-white B2B SaaS template: stock Tailwind blue (#2563eb), pure
white cards, soft drop shadows, pastel badge soup, hero-metric dashboards. Also:
consumer-playful gradients, decorative glassmorphism, anything that reads "AI made
this dashboard." If the palette is guessable from the category alone (B2B tool implies
blue), it has failed.

## Design Principles

1. Instrument over decoration. Every element serves reading or acting on data. No
   ornament that does not aid the task.
2. Data legibility first. Machine identifiers (ASN, email, handle, IDs) use tabular
   monospace and align; tables stay dense but scannable; hierarchy is unmistakable.
3. One committed accent, used sparingly. A single non-blue accent carries meaning
   (primary action, active nav, focus). Neutrals do the rest. Status is a restrained,
   low-chroma set, never a rainbow of pastels.
4. Trustworthy state. Every interactive element has honest hover, focus, disabled,
   loading, empty, and error states. Nothing looks broken or ambiguous.
5. True to the domain. The visual language should feel native to network operations
   and infrastructure, not interchangeable with any random CRM.

## Accessibility & Inclusion

Target WCAG AA contrast for text and controls. Keyboard focus is always visible.
Respect prefers-reduced-motion. Never encode status by color alone; pair it with text
or shape. Chinese is the primary language, so the type stack must render CJK cleanly
alongside the Latin / monospace data.
