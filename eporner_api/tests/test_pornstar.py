import pytest
from ..api import Client
from base_api import BaseCore

@pytest.mark.asyncio
async def test_pornstar():
    url = "https://www.eporner.com/pornstar/riley-reid/"
    core = BaseCore()
    core.configuration.pages_concurrency = 1
    core.configuration.videos_concurrency = 1
    client = Client(core)
    pornstar = await client.get_pornstar(url, load_html=True)

    videos = pornstar.videos(pages=1)
    
    idx = 0
    async for result in videos:
        video = result.unwrap()
        assert isinstance(video.title, str) and len(video.title) > 3
        idx += 1
        if idx == 5:
            break


    assert isinstance(pornstar.pornstar_rank, str) and len(pornstar.pornstar_rank) >= 1
    assert isinstance(pornstar.aliases, list) and len(pornstar.aliases) > 1
    assert isinstance(pornstar.biography, str) and len(pornstar.biography) > 10
    assert isinstance(pornstar.age, str) and len(pornstar.age) >= 2
    assert isinstance(pornstar.cup, str) and len(pornstar.cup) >= 1
    assert isinstance(pornstar.country, str) and len(pornstar.country) >= 2
    assert isinstance(pornstar.weight, str) and len(pornstar.weight) >= 2
    assert isinstance(pornstar.name, str) and len(pornstar.name) >= 2
    assert isinstance(pornstar.eye_color, str) and len(pornstar.eye_color) >= 2
    assert isinstance(pornstar.measurements, str) and len(pornstar.measurements) >= 2
    assert isinstance(pornstar.profile_views, str) and len(pornstar.profile_views) >= 2
    assert isinstance(pornstar.video_views, str) and len(pornstar.video_views) >= 2
    assert isinstance(pornstar.photo_views, str) and len(pornstar.photo_views) >= 2
    assert isinstance(pornstar.subscribers, str) and len(pornstar.subscribers) >= 2
    assert isinstance(pornstar.photos_amount, str) and len(pornstar.photos_amount) >= 2
    assert isinstance(pornstar.video_amount, str) and len(pornstar.video_amount) >= 2
    assert isinstance(pornstar.picture, str) and len(pornstar.picture) >= 2
    assert isinstance(pornstar.pornstar_id, str) and len(pornstar.pornstar_id) >= 1
    assert isinstance(pornstar.websites, dict) and len(pornstar.websites) >= 1


def test_pornstar_extract_html_violet_myers():
    from ..api import Pornstar

    html = """<div id="pornstarbio">
<div class="psbio ps1">
<h1 style="font-size:35px;">Violet Myers</h1>
<div id="pornstarsubscribe"><div class="subscribebutton " data-subscribed="no" onclick="EP.subscribe.sub(this, 31375, 'pornstar')">Subscribe <small>(31,273)</small></div></div>
<div class="psImgOuter">
<img src="https://static-eu-cdn.eporner.com/gallery/Cm/mY/2xbSWTsmYCm/32216333-violet-myers-pic594_880x660.jpg" alt="Violet Myers">
<div class="aspectholder"><div style="padding-top:66.704545454545%"></div></div> <div class="ps1a"><a href="#toptopbel">Videos<span>182</span></a><a href="/pornstar/violet-myers-k5LhR/photos/#toptopbel">Photos<span>86</span></a></div>
</div>
</div>
<div class="psbio ps3">
<div>Rank:<span>3</span></div><div>Profile views:<span>17,022,198</span></div><div>Video views:<span>260,456,558</span></div><div>Photo views:<span>2,709,450</span></div><div id="resppssubcnt">Subscribers:<span>31,273</span></div>
</div>
<div class="psbio ps2">
<ul>
<li><span>Country:</span><div class="cllnumber">United States</div></li> <li><span>Age:</span><div class="cllnumber">29</div></li> <li><span>Ethnicity:</span><div class="cllnumber">Latin</div></li> <li><span>Eye:</span><div class="cllnumber">Brown</div></li> <li><span>Hair:</span><div class="cllnumber">Black</div></li> <li><span>Height:</span><div class="cllnumber">160 cm / 5'3"</div></li> <li><span>Weight:</span><div class="cllnumber">67 kg / 148 lbs</div></li> <li><span>Cup:</span><div class="cllnumber">34F</div></li> <li><span>Measurements:</span><div class="cllnumber">34-28-36</div></li> </ul>
</div>
<div class="psbio ps4">
<h3>Violet Myers&nbsp; Aliases:</h3>
<div class="psscrol">
<ul class="psbioaliases"><li>Luna Bunny</li><li>Violet Meyers</li></ul></div> </div>
<div class="psbio ps5">
<h3>Violet Myers&nbsp; Websites:</h3>
<ul class="pswebsites"><li><i class="fa fa-external-link-square"></i> <a href="http://violetthe13th.com/" rel="noopener">Official Website</a></li></ul>
</div>
<div class="psbio ps6 psnone">
</div>
<div class="clear"></div>
</div>"""

    data = Pornstar._extract_html(html)
    assert data["name"] == "Violet Myers"
    assert data["pornstar_id"] == "31375"
    assert data["subscribers"] == "31,273"
    assert data["picture"] == "https://static-eu-cdn.eporner.com/gallery/Cm/mY/2xbSWTsmYCm/32216333-violet-myers-pic594_880x660.jpg"
    assert data["video_amount"] == "182"
    assert data["photos_amount"] == "86"
    assert data["pornstar_rank"] == "3"
    assert data["profile_views"] == "17,022,198"
    assert data["video_views"] == "260,456,558"
    assert data["photo_views"] == "2,709,450"
    assert data["country"] == "United States"
    assert data["age"] == "29"
    assert data["ethnicity"] == "Latin"
    assert data["eye_color"] == "Brown"
    assert data["hair_color"] == "Black"
    assert data["height"] == '160 cm / 5\'3"'
    assert data["weight"] == "67 kg / 148 lbs"
    assert data["cup"] == "34F"
    assert data["measurements"] == "34-28-36"
    assert data["biography"] is None
    assert data["aliases"] == ["Luna Bunny", "Violet Meyers"]
    assert data["websites"] == {"Official Website": "http://violetthe13th.com/"}


def test_pornstar_graceful_fallbacks():
    from ..api import Pornstar

    data = Pornstar._extract_html("<div id='pornstarbio'></div>")
    assert data["name"] is None
    assert data["pornstar_id"] is None
    assert data["subscribers"] is None
    assert data["picture"] is None
    assert data["video_amount"] is None
    assert data["photos_amount"] is None
    assert data["pornstar_rank"] is None
    assert data["profile_views"] is None
    assert data["video_views"] is None
    assert data["photo_views"] is None
    assert data["country"] is None
    assert data["age"] is None
    assert data["ethnicity"] is None
    assert data["eye_color"] is None
    assert data["hair_color"] is None
    assert data["height"] is None
    assert data["weight"] is None
    assert data["cup"] is None
    assert data["measurements"] is None
    assert data["biography"] is None
    assert data["aliases"] == []
    assert data["websites"] == {}
