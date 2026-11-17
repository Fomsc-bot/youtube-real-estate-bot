# BTS long-form content and research plan

## Research findings and editorial approach

The long-form workflow is designed for thoughtful BTS fan commentary for adult women and ARMY. It discusses the appeal of members' public artistry, stage presence, humor, teamwork, and public moments as fan interpretation. It does not speculate about private relationships or suggest that a member knows or loves the viewer.

Recommended episode formats:

1. **Why a public BTS moment resonates with fans** — start with one verifiable event, then explain what viewers may find compelling about it.
2. **A member's public artistry** — examine songwriting, performance choices, or an interview, clearly separating reported facts from the host's opinion.
3. **BTS group chemistry** — explore publicly documented teamwork and creative roles, with one concrete example per section.

Use a direct cold open, promise the episode's payoff in the first 30 seconds, and build five distinct chapters. Aim for 8–10 minutes and 1,150–1,450 spoken words. Do not stretch a short news item to fill time; choose a topic with enough evidence and original commentary. Use a natural subscribe invitation once and end with a specific fan question.

## Automatic research collection

The workflow collects recent BTS-tagged RSS items from its configured publishers, then uses the language model to choose a topic and a coherent set of at least three articles. It builds the evidence notes directly from the publishers' RSS headlines and excerpts and saves the chosen URLs, excerpts, and topic in `output/longform/research.json`. No research fields are needed in the workflow form.

RSS excerpts are attributed source material, not independent verification. Review the linked publisher pages and correct any errors or context gaps in the generated script before publishing. Exclude dating rumors, leaked/private material, unverified fan claims, and unsupported personality assertions. The generated episode should distinguish reported facts from fan interpretation.

Use the workflow's dry-run setting first (the default). Review the research bundle, generated script, image credits, video, and thumbnail before choosing `dry_run=false` to publish publicly.

## Rendering and rights

The renderer uses distinct photos retrieved from Wikimedia Commons only when the file metadata identifies a CC BY, CC0, or public-domain license. The description includes the creator, license, and source page for every photo. It uses one licensed image per chapter, with the full photo centered over a blurred copy of itself; it does not use BTS music videos, performance footage, or songs. Commons metadata is not a guarantee that a file was uploaded correctly, so inspect each attribution and image before publishing. A public-domain or Creative Commons label on a photo does not grant rights to a song, video clip, logo, or other work shown in it.

Long-form videos need original commentary and meaningful variation between episodes. YouTube says repetitive, mass-produced scripts and image slideshows with little narrative value may be ineligible for monetization. Copyright claims can also affect reused media, and fair use is decided case by case. This workflow does not guarantee YPP approval.

## Watch-hour goal and learning loop

The ad-revenue YPP threshold currently includes 1,000 subscribers and 4,000 qualified public watch hours in the prior 12 months. Shorts-feed watch time does not count toward those 4,000 hours. For scale, 4,000 hours is 240,000 minutes; at an 8-minute average view duration, that would take about 30,000 views across eligible public long-form videos. Actual average duration will vary, and the threshold does not guarantee acceptance.

Use one well-researched episode per week as a starting experiment; the workflow is manual so research and quality can guide each release. After 1–2 days, compare impressions click-through rate, how many viewers remain at 30 seconds, average view duration, watch time, and subscribers gained. YouTube's retention report highlights top moments and drop-offs; use those to choose the next episode's opening and pacing. Compare similar videos and change one thing at a time.

## YouTube references

- [YPP eligibility and qualified watch hours](https://support.google.com/youtube/answer/72851)
- [YouTube channel monetization policies: inauthentic and reused content](https://support.google.com/youtube/answer/1311392)
- [Audience retention report and intro guidance](https://support.google.com/youtube/answer/9314415)
- [YouTube copyright and fair use information](https://support.google.com/youtube/answer/9783148)
- [Wikimedia Commons image licensing metadata API](https://www.mediawiki.org/wiki/API:Imageinfo)
