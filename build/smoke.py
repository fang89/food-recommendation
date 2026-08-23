#!/usr/bin/env python3
"""Execute the built page's script against stubbed Leaflet and DOM.

    python3 build/smoke.py

Syntax checks pass happily on code that throws the moment it runs. This runs the
real script - including draw() and the initial fitBounds - with every Leaflet and
DOM call stubbed, so a reference to something the data no longer has (the kind of
error that renders a blank map and an empty table) fails the build instead.

It proves the plumbing executes. It says nothing about how the page looks.
"""
import os, re, shutil, subprocess, sys, tempfile


def engine():
    """Whatever JS engine is to hand: node on CI, osascript on macOS."""
    if shutil.which("node"):
        return ["node"], "node"
    if shutil.which("osascript"):
        return ["osascript", "-l", "JavaScript"], "osascript"
    sys.exit("no JS engine found - install node, or run this on macOS")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "index.html")

STUBS = r"""
var __calls = {};
function note(n){ __calls[n] = (__calls[n]||0)+1; }

function El(id){
  this.id=id; this.dataset={}; this.style={}; this._html="";
  this.classList={ toggle:function(){}, add:function(){}, remove:function(){}, contains:function(){return false} };
}
// Keep every listener, not the last one: the page attaches two click handlers
// to the map container, and a stub that overwrote one would test a page that
// does not exist.
El.prototype.addEventListener=function(ev,fn){
  var m=(this._on || (this._on={}));
  (m[ev] || (m[ev]=[])).push(fn);
};
El.prototype.fire=function(ev,obj){
  var fns=this._on && this._on[ev];
  if(!fns) return false;
  obj=obj||{}; if(!obj.target) obj.target=this;
  for(var i=0;i<fns.length;i++) fns[i](obj);
  return true;
};
El.prototype.click=function(){ this.fire("click"); };
El.prototype.setAttribute=function(){};
El.prototype.getAttribute=function(){return null};
El.prototype.removeAttribute=function(){};
El.prototype.querySelector=function(){return new El("q")};
El.prototype.querySelectorAll=function(){return []};
El.prototype.closest=function(){return null};
El.prototype.appendChild=function(){};
Object.defineProperty(El.prototype,"innerHTML",{
  get:function(){return this._html}, set:function(v){ this._html=String(v); note("html:"+this.id); }});
Object.defineProperty(El.prototype,"textContent",{ get:function(){return ""}, set:function(){} });

var __els={};
var document={
  documentElement:new El("root"),
  getElementById:function(id){ return __els[id] || (__els[id]=new El(id)); },
  querySelector:function(){ return new El("sel"); },
  querySelectorAll:function(){ return []; },
  createElement:function(){ return new El("new"); }
};
var window={
  console:{error:function(){}, log:function(){}},
  matchMedia:function(){ return {matches:false, addEventListener:function(){}, addListener:function(){}}; }
};
window.window=window;
var __out=(typeof process!=="undefined"&&process.stdout)
  ? function(t){ process.stdout.write(t+"\n"); } : function(){};
var console=window.console;
// No event loop here, so a timer fires at once. Same bargain as SP below: work
// the page defers has to have happened by the time the checks run.
var __timers=0;
function setTimeout(fn){ __timers++; fn(); return __timers; }
function clearTimeout(){}
var navigator={platform:"MacIntel", userAgent:"smoke"};
function getComputedStyle(){ return {getPropertyValue:function(){return "#000"}}; }
function MutationObserver(fn){ this.observe=function(){}; }

function Layer(kind){ note(kind); }
Layer.prototype.addTo=function(){ return this; };
Layer.prototype.bindTooltip=function(){ return this; };
Layer.prototype.bindPopup=function(){ return this; };
Layer.prototype.on=function(){ return this; };
Layer.prototype.off=function(){ return this; };
Layer.prototype.setStyle=function(){ return this; };
Layer.prototype.setRadius=function(){ return this; };
Layer.prototype.setTooltipContent=function(){ return this; };
Layer.prototype.setPopupContent=function(){ return this; };
Layer.prototype.openPopup=function(){ return this; };
Layer.prototype.getTooltip=function(){ return {getElement:function(){ return new El("tip"); }}; };
Layer.prototype.getElement=function(){ return new El("path"); };
Layer.prototype.clearLayers=function(){ return this; };
Layer.prototype.bringToBack=function(){ return this; };
Layer.prototype.addLayer=function(){ return this; };

function Bounds(){ }
Bounds.prototype.pad=function(){ return this; };
Bounds.prototype.contains=function(){ return true; };

var __mapc=new El("mapc"), __zoom=16;
var L={
  latLngBounds:function(){ note("latLngBounds"); return new Bounds(); },
  layerGroup:function(){ return new Layer("layerGroup"); },
  circleMarker:function(){ return new Layer("circleMarker"); },
  marker:function(){ return new Layer("marker"); },
  circle:function(){ return new Layer("circle"); },
  polyline:function(){ return new Layer("polyline"); },
  divIcon:function(){ return {}; },
  tooltip:function(){ return new Layer("tooltip"); },
  map:function(){
    note("map");
    return {
      on:function(){}, off:function(){},
      // One container, not a fresh stub per call - the checks below have to
      // reach the very listeners the page attached.
      getContainer:function(){ return __mapc; },
      getZoom:function(){ return __zoom; },
      fitBounds:function(){ note("fitBounds"); },
      setView:function(){ note("setView"); }, removeLayer:function(){}, addLayer:function(){},
      invalidateSize:function(){},
      attributionControl:{setPrefix:function(){ note("attrPrefix"); }},
      dragging:{enable:function(){ note("drag:on"); }, disable:function(){ note("drag:off"); }},
      setZoomAround:function(pt,z){ note("setZoomAround"); __zoom=z; },
      mouseEventToContainerPoint:function(){ return {x:200,y:200}; },
      scrollWheelZoom:{enable:function(){}, disable:function(){}}
    };
  }
};
L.tileLayer=function(){ note("tileLayer"); return new Layer("tileLayer"); };
L.TileLayer=function(){};
L.TileLayer.prototype.initialize=function(){};
L.TileLayer.prototype.addTo=function(){ return this; };
L.TileLayer.prototype.bringToBack=function(){ return this; };
L.TileLayer.prototype._getZoomForUrl=function(){ return 16; };
L.TileLayer.extend=function(proto){
  var C=function(){ this._theme=arguments[0]; if(proto.initialize) proto.initialize.apply(this,arguments); };
  C.prototype=Object.create(L.TileLayer.prototype);
  for(var k in proto) C.prototype[k]=proto[k];
  return C;
};
var TILES={};

// Synchronous stand-in for Promise: settles inline so the pull chain finishes
// before the checks below run. Same surface the page uses - then/catch/resolve.
function SP(state,value){ this.s=state; this.v=value; }
SP.resolve=function(v){ return (v && v.then) ? v : new SP("ok",v); };
SP.reject =function(e){ return new SP("no",e); };
SP.prototype.then=function(ok,bad){
  try{
    if(this.s==="ok") return ok ? SP.resolve(ok(this.v)) : this;
    if(bad) return SP.resolve(bad(this.v));
    return this;
  }catch(e){ return SP.reject(e); }
};
SP.prototype["catch"]=function(bad){ return this.then(null,bad); };
var Promise=SP;

var SHEET_CSV=[
  ",,,,,,,,",
  ",Food places,,,,,,,",
  ",,,,,,,,",
  ",Name of place,Signature dish tried,Plus,Minus,Rating (5 pt system),Price band,Link / Address,Other comments",
  ",Smoke Cafe,toast,\"bright, cheap\",queue,4.5,$,\"1 Test Rd, Singapore 209263\",",
  ",Rating Slipped,noodles,good,4.0,,$$,\"2 Test Rd, Singapore 338731\",",
  ",\"Comma, Inc\",rice,,,3.0,$,\"3 Test Rd, Singapore 208905\",",
  ",Slipped Twice,curry,3.5,,,$,\"4 Test Rd, Singapore 207561\","
].join("\n");

var __fetched=[];
function fetch(url){
  __fetched.push(url);
  if(url.indexOf("docs.google.com")>=0){
    if(url.indexOf("export?format=csv")<0)
      return SP.reject(new Error(
        "SHEET_CSV is a capture of /export?format=csv, but the page asked for "+
        url+" - gviz folds the title row into the header and blanks the Rating "+
        "header, so this fixture would not represent what it returns"));
    note("fetch:sheet");
    return SP.resolve({ok:true, status:200, text:function(){ return SP.resolve(SHEET_CSV); }});
  }
  if(url.indexOf("onemap.gov.sg")>=0){
    note("fetch:onemap");
    return SP.resolve({ok:true, status:200, json:function(){
      return SP.resolve({results:[{LATITUDE:"1.3180",LONGITUDE:"103.8640",ADDRESS:"STUB"}]});
    }});
  }
  return SP.reject(new Error("unexpected fetch: "+url));
}
"""

CHECKS = r"""
if(__els["map"] && /failed to draw/.test(__els["map"].innerHTML))
  throw new Error("the page caught its own error and painted the apology: "+
                  String(__els["map"].innerHTML).replace(/<[^>]*>/g," ").slice(0,220));
if(!__calls["map"])       throw new Error("map was never created");
if(!__calls["attrPrefix"]) throw new Error("the attribution prefix was left at Leaflet's default, which carries the flag");

// Zoom gestures. A plain wheel has to fall through to the page - the map is a
// tall panel mid-page, and a map that eats the scroll strands the reader on it.
function __wheel(mod){
  var swallowed=false;
  __mapc.fire("wheel",{ctrlKey:mod, metaKey:false, deltaY:-300, deltaMode:0,
                       preventDefault:function(){ swallowed=true; }});
  return swallowed;
}
__calls["setZoomAround"]=0;
if(__wheel(false)) throw new Error("a plain wheel over the map was swallowed - the page can no longer be scrolled past the map");
if(__calls["setZoomAround"]) throw new Error("a plain wheel zoomed the map, so scrolling the page over it is impossible");
if(!__wheel(true)) throw new Error("Cmd/Ctrl + wheel was not taken by the map, so the browser will zoom the whole page instead");
if(!__calls["setZoomAround"]) throw new Error("Cmd/Ctrl + wheel did not zoom the map");
var __before=__zoom;
__wheel(true); __wheel(true);
if(__zoom<=__before) throw new Error("wheeling up did not zoom in");
// Clicking the map is consent: from then on the bare wheel zooms it.
__mapc.fire("click");
__calls["setZoomAround"]=0;
if(!__wheel(false) || !__calls["setZoomAround"])
  throw new Error("after clicking the map, a plain wheel still does not zoom it");
if(__calls["drag:off"]) throw new Error("dragging was disabled on a fine pointer - a mouse must still be able to pan");
if(!__calls["fitBounds"]) throw new Error("fitBounds never ran - the page would open blank");
if(!__calls["html:rows"]) throw new Error("the table body was never written - the list would be empty");
if(!__calls["html:switch"]) throw new Error("the datum switch was never written");
if(!__calls["circleMarker"]) throw new Error("no place markers were created");
if(!__calls["tileLayer"]) throw new Error("no basemap layer was added");

// Selecting a place must recentre on it, the same as switching datum does.
if(PLACES.length){
  var pv=__calls["setView"]||0;
  select(PLACES[0].id);
  if((__calls["setView"]||0)<=pv)
    throw new Error("selecting a place did not recentre the map on it");
  select(null);
}

// Every home the build kept must be plottable, and switching to one must both
// change the datum and recentre the map on it.
HOMES.forEach(function(h){
  if(typeof h.lat!=="number" || typeof h.lng!=="number")
    throw new Error("home " + h.name + " has no coordinates");
});
if(HOMES.length>1){
  var views=__calls["setView"]||0, was=state.home;
  setHome(was===0?1:0);
  if(state.home===was) throw new Error("switching home did not change the datum");
  if((__calls["setView"]||0)<=views)
    throw new Error("switching home did not recentre the map on that home");
}

// The "Pull from sheet" button must survive a whole round trip: fetch the CSV,
// parse it, geocode the rows this build has never seen, redraw the table.
var built = __calls["html:rows"];
__els["pull"].click();
if(!__calls["fetch:sheet"])
  throw new Error("Pull from sheet never fetched the sheet");
if(!__calls["fetch:onemap"])
  throw new Error("Pull from sheet never geocoded the rows it did not recognise");
if(__calls["html:rows"] <= built)
  throw new Error("Pull from sheet ran but never redrew the table");
var said = __els["pullnote"]._html;
if(/Could not pull/.test(said))
  throw new Error("Pull from sheet failed: " + said);
if(!/4 new/.test(said))
  throw new Error("Pull from sheet misread the CSV, it reported: " + said);

// Row-count alone hides a column-mapping bug: a header the parser cannot match
// yields rows with every rating 0 and every price "$", and still counts them.
var pulled={}; PLACES.forEach(function(p){ pulled[p.name]=p; });
if(!pulled["Smoke Cafe"] || pulled["Smoke Cafe"].rating!==4.5)
  throw new Error("the Rating column was not read - Smoke Cafe came back as " +
                  (pulled["Smoke Cafe"] && pulled["Smoke Cafe"].rating));
if(!pulled["Comma, Inc"] || pulled["Comma, Inc"].price!=="$")
  throw new Error("the Price column was not read - quoted-comma row came back as " +
                  (pulled["Comma, Inc"] && pulled["Comma, Inc"].price));
if(pulled["Smoke Cafe"].dish!=="toast")
  throw new Error("the Signature dish column was not read");
if(pulled["Smoke Cafe"].plus!=="bright, cheap")
  throw new Error("a quoted comma broke the CSV parser");
// Ratings that slipped left must be recovered - one column, and two.
if(!pulled["Rating Slipped"] || pulled["Rating Slipped"].rating!==4)
  throw new Error("a rating left in the Minus column was not recovered");
if(!pulled["Slipped Twice"] || pulled["Slipped Twice"].rating!==3.5)
  throw new Error("a rating left in the Plus column was not recovered - got " +
                  (pulled["Slipped Twice"] && pulled["Slipped Twice"].rating));
if(pulled["Slipped Twice"].plus!=="")
  throw new Error("a rating recovered from Plus was left behind in Plus as well");

"ok " + __calls["circleMarker"] + " markers, " + __calls["circle"] + " rings, " +
  HOMES.length + " homes, pull ok";
"""


def main():
    if not os.path.exists(PAGE):
        sys.exit("index.html not found - run build/build.py first")
    html = open(PAGE).read()

    start = html.rindex("<script>\n(function(){")
    body = html[start:].split("<script>", 1)[1]
    body = body[:body.rindex("</script>")]

    # Unwrap the page's IIFE so its variables land at the top level of the test
    # file. The checks can then read PLACES and friends directly, instead of the
    # page having to carry a test hook it does not otherwise need.
    head, tail = body.index("(function(){") + len("(function(){"), body.rindex("})();")
    body = body[head:tail]

    cmd, kind = engine()
    # osascript reports the script's last expression; node has to be told to
    # print it, and through __out, since the stubs shadow console.
    tail = CHECKS if kind == "osascript" else CHECKS.replace(
        '\n"ok "', '\n__out("ok "', 1).rstrip().rstrip(";") + ");"

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(STUBS + body + tail)
        path = fh.name
    try:
        run = subprocess.run(cmd + [path],
                             capture_output=True, text=True)
    finally:
        os.unlink(path)

    out = (run.stdout or "").strip()
    err = (run.stderr or "").strip()
    if run.returncode != 0 or not out.startswith("ok"):
        print("SMOKE TEST FAILED")
        print(err or out)
        sys.exit(1)
    print("smoke test passed - " + out[3:])


if __name__ == "__main__":
    main()
