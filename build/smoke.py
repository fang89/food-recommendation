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
El.prototype.addEventListener=function(ev,fn){
  (this._on || (this._on={}))[ev] = fn;
};
El.prototype.click=function(){ if(this._on&&this._on.click) this._on.click({target:this}); };
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
      getContainer:function(){ return new El("mapc"); },
      getZoom:function(){ return 16; },
      fitBounds:function(){ note("fitBounds"); },
      setView:function(){}, removeLayer:function(){}, addLayer:function(){},
      invalidateSize:function(){},
      scrollWheelZoom:{enable:function(){}, disable:function(){}}
    };
  }
};
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
  "House postal code,,,,",
  "Name of place,Signature dish,Plus,Minus,Rating,Price,Link / Address",
  "Smoke Cafe,toast,\"bright, cheap\",queue,4.5,$,\"1 Test Rd, Singapore 209263\"",
  "Rating Slipped,noodles,good,4.0,,$$,\"2 Test Rd, Singapore 338731\"",
  "\"Comma, Inc\",rice,,,3.0,$,\"3 Test Rd, Singapore 208905\""
].join("\n");

var __fetched=[];
function fetch(url){
  __fetched.push(url);
  if(url.indexOf("docs.google.com")>=0){
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
if(!__calls["map"])       throw new Error("map was never created");
if(!__calls["fitBounds"]) throw new Error("fitBounds never ran - the page would open blank");
if(!__calls["html:rows"]) throw new Error("the table body was never written - the list would be empty");
if(!__calls["html:switch"]) throw new Error("the datum switch was never written");
if(!__calls["circleMarker"]) throw new Error("no place markers were created");

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
if(!/3 new/.test(said))
  throw new Error("Pull from sheet misread the CSV, it reported: " + said);

"ok " + __calls["circleMarker"] + " markers, " + __calls["circle"] + " rings, pull ok";
"""


def main():
    if not os.path.exists(PAGE):
        sys.exit("index.html not found - run build/build.py first")
    html = open(PAGE).read()

    start = html.rindex("<script>\n(function(){")
    body = html[start:].split("<script>", 1)[1]
    body = body[:body.rindex("</script>")]

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
