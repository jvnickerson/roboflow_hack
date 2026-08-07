# Bird cams around New York City

_Research compiled by Claude Code, 2026-08-07. Every status below was checked between 5:50 and 6:15 PM ET that evening by pulling the stream or opening the operator's page in a browser. Every URL was re-checked for a 200 at 6:25 PM. Directory listings of bird cams are largely stale, so none of this comes from one._

[Streaming now](#streaming-now) · [Raw stream endpoints](#raw-stream-endpoints) · [Off for the season](#off-for-the-season) · [Retired or removed](#retired-or-removed) · [Outside the metro ring](#outside-the-metro-ring) · [Sources out of reach](#sources-out-of-reach)

---

## Streaming now

Six cams in the metro area were serving video at check time. One sits inside the five boroughs.

| Cam | Where | Species | Watch | Status at check |
|---|---|---|---|---|
| Falcon Cam, 55 Water Street | Lower Manhattan, 14th-floor ledge over New York Harbor | Peregrine falcon | [55water.com/falcon-cam](https://www.55water.com/falcon-cam/) | HLS playlist served. A pulled frame shows an empty nest box with the harbor behind it. Self-hosted datarhei restreamer on Azure |
| Osprey Cam | Oyster Bay, Nassau County | Osprey | [youtube.com/watch?v=ZzW9-t5bYJE](https://www.youtube.com/watch?v=ZzW9-t5bYJE) · [operator page](https://www.psegliny.com/wildlife/osprey/ospreycams) | `isLiveNow: true`. 4K with infrared, PSEG Long Island. Operator lists the season as March 15 to October 19 |
| MNSA Peregrine-Cam | Marine Nature Study Area, Oceanside, Town of Hempstead | Peregrine falcon | [youtube.com/watch?v=iNj5nT47fX0](https://www.youtube.com/watch?v=iNj5nT47fX0) · [operator page](https://hempsteadny.gov/358/Peregrine-Falcon-Nest-Cam) | `isLiveNow: true`. The town page describes the pair as year-round marsh residents |
| Union County Falcon Cam | Union County Courthouse roof, Elizabeth NJ | Peregrine falcon | [youtube.com/watch?v=4t2TxgM8YQs](https://www.youtube.com/watch?v=4t2TxgM8YQs) · [operator page](https://ucnj.org/falcon-camera/) | `isLiveNow: true`. Union County with Phillips 66. Two chicks were banded and fledged this June |
| Duke Farms Eagle Cam | Hillsborough NJ | Bald eagle | [youtube.com/user/dukefarmsfdn/live](https://www.youtube.com/user/dukefarmsfdn/live) · [operator page](https://www.dukefarms.org/eagle-cam/) | `isLiveNow: true`. The page says 24/7, year-round. One eaglet hatched February 22, 2026 |
| GMMCB Falcon Cam | Governor Mario M. Cuomo Bridge, Tarrytown–Nyack | Peregrine falcon | [content3.thruway.ny.gov/falcon](https://content3.thruway.ny.gov/falcon/) | Playlist serves and video advances in real time. See the timestamp note below. NY Thruway Authority over NYSDOT skyvdn |

The Thruway falcon page is normally linked as `thruway.ny.gov/falcon/`, which 403s automated requests and redirects a browser to the `content3` host above.

### The Cuomo Bridge timestamp

The stream is up and moving: two frames pulled 75 seconds apart carried burned-in timestamps 75 seconds apart. Both read **10/13/2025**. The nest box is empty. Either the feed is replaying October 2025 footage or the camera's clock is badly off. The Thruway page offers date and time dropdowns for archived playback, which makes replay plausible without settling it.

### Licensing note

The 55 Water Street player config declares `"license": "CC BY 4.0", "title": "Birdcam"`. That is the operator's own declaration inside the embed config. The page itself carries no terms of use.

---

## Raw stream endpoints

Two cams expose an unauthenticated HLS playlist that ffmpeg or OpenCV can read directly.

**55 Water Street.** Master playlist, no key, no token:
`https://nws-restreamer-1.eastus.cloudapp.azure.com/memfs/0e7bf1d1-4f35-4da1-a5c8-ff904f082dda.m3u8`
Poster still, refreshed server-side: same path ending `.jpg`

**Cuomo Bridge.** Master playlist, no key:
`https://s58.nysdot.skyvdn.com/rtplive/TA_Falcon/playlist.m3u8`

The four YouTube cams need `yt-dlp` or the embed player. The Town of Hempstead page embeds the MNSA cam as a channel-level `live_stream` (channel `UCix4ihYdgo-LYuHwV18gWyA`), so its video ID may rotate.

---

## Off for the season

**Bayonne Bridge FalconCam.** [panynj.gov](https://www.panynj.gov/bridges-tunnels/en/bayonne-bridge/falcon-cam.html). Port Authority of NY & NJ with EarthCam, on a nesting tower in the Kill Van Kull beside the bridge, between Staten Island's north shore and Bayonne. Read directly off the page:

> The Peregrine Falcons have left the nest for the season! We are anticipating their return in March 2027.

That page carries no player. [EarthCam's Staten Island directory](https://www.earthcam.com/usa/newyork/statenisland/?cam=falcon_panynj) still lists a "Falcon Cam" tile with live weather and a view count, so a stream object may persist there even though the source page says the season is over.

**Connecticut Audubon at Milford Point.** An [osprey cam](https://ctaudubon.org/conservation/science/bird-cams/milford-point-osprey-cam/) and a [purple martin cam](https://ctaudubon.org/conservation/science/bird-cams/milford-point-purple-martin-cam/) inside a nesting gourd, both Angelcam-hosted. The page reads "Our Osprey Cam is live," and the operator describes the season as April through fledging in late summer. A probe of the Angelcam HLS returned 401, so the token is short-lived and tied to the iframe session.

---

## Retired or removed

| Cam | Link | What happened |
|---|---|---|
| OspreyZone, Cutchogue, North Fork | [ospreyzone.com](https://ospreyzone.com/) | Camera physically removed. A visitor reported the equipment gone in May 2024 and an admin confirmed it. The site now plays archived clips behind a notice about "lack of visibility on the live stream" |
| PSEG Patchogue osprey cam | [psegliny.com](https://www.psegliny.com/wildlife/osprey/ospreycams) | Platform relocated away from nearby construction. PSEG says the Patchogue camera is no longer available |
| Jersey City peregrine cam, 101 Hudson Street | [conservewildlifenj.org](https://conservewildlifenj.org/projects/falcon/) | Ran roughly 20 years from a nest box on the roof. Conserve Wildlife NJ describes the nest as currently inactive |
| NYU hawk cam, Bobst Library, Washington Square | none found | On and off since 2011. NYU shut it down in 2014 and restored it in 2017. No current live feed surfaced in this search |
| Greenwich osprey cam, Audubon Connecticut | [ct.audubon.org/audubon-live](https://ct.audubon.org/audubon-live) | Now redirects to a Connecticut birds page with no cams on it. Only YouTube highlight clips remain |

---

## Outside the metro ring

Farther out, still New York or New Jersey:

- **Conserve Wildlife NJ.** An [osprey cam](https://conservewildlifenj.org/wildlife-cams/ospreycam/) at Barnegat Light on Long Beach Island, plus one at Island Beach State Park. The Barnegat nest is described as most active March through August.
- **Cornell Lab Bird Cams, Ithaca.** [youtube.com/@CornellBirdCams](https://www.youtube.com/@CornellBirdCams). The largest operation in the state, five to twelve cameras running year-round: the red-tailed hawk nest on the Cornell athletic field light towers (Big Red), the Sapsucker Woods FeederWatch cam, barred owls, great horned owls, ospreys. Their own index at `allaboutbirds.org/cams/` blocks automated requests.
- **Rochester peregrines.** [rfalconcam.com](https://rfalconcam.com/rfc-main/streamView.php), nine cameras on the Times Square Building.
- **Utica peregrines.** [hdontap.com](https://hdontap.com/stream/252045/utica-falcons-nest-box-live-webcam/).

---

## Sources out of reach

- **allaboutbirds.org returns 403 to automated requests** (Cloudflare). The Cornell list above comes from secondary reporting and their YouTube channel rather than their own cam index.
- **EarthCam's stream endpoints load through JavaScript**, so whether the Staten Island falcon tile resolves to a working stream or a placeholder stayed unconfirmed.
- **Angelcam streams are token-gated** per iframe session, which left Milford Point's liveness unverified.
- **Not searched:** cams hosted only on Facebook or Instagram, school and university cams that are not publicly indexed, and any nest cams run by NYC Parks or the Bronx Zoo that do not appear in web search. NYC Bird Alliance runs a 25-camera trap network across 40-plus nests, but those are research cameras with no public feed.
