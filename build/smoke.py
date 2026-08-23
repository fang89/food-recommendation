#!/usr/bin/env python3
"""Execute the built page's script against stubbed Leaflet and DOM.

    python3 build/smoke.py

Syntax checks pass happily on code that throws the moment it runs. This runs the
real script - including draw() and the initial fitBounds - with every Leaflet and
DOM call stubbed, so a reference to something the data no longer has (the kind of
error that renders a blank map and an empty table) fails the build instead.

It proves the plumbing executes. It says nothing about how the page looks.
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "index.html")

STUBS = r"""
var __calls = {};
function note(n){ __calls[n] = (__calls[n]||0)+1; }

function El(id){
  this.id=id; this.dataset={}; this.style={}; this._html="";
  this.classList={ toggle:function(){}, add:function(){}, remove:function(){}, contains:function(){return false} };
}
El.prototype.addEventListener=function(){};
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

var document={
  documentElement:new El("root"),
  getElementById:function(id){ return new El(id); },
  querySelector:function(){ return new El("sel"); },
  querySelectorAll:function(){ return []; },
  createElement:function(){ return new El("new"); }
};
var window={
  console:{error:function(){}, log:function(){}},
  matchMedia:function(){ return {matches:false, addEventListener:function(){}, addListener:function(){}}; }
};
window.window=window;
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
"""

CHECKS = r"""
if(!__calls["map"])       throw new Error("map was never created");
if(!__calls["fitBounds"]) throw new Error("fitBounds never ran - the page would open blank");
if(!__calls["html:rows"]) throw new Error("the table body was never written - the list would be empty");
if(!__calls["html:switch"]) throw new Error("the datum switch was never written");
if(!__calls["circleMarker"]) throw new Error("no place markers were created");
"ok " + __calls["circleMarker"] + " markers, " + __calls["circle"] + " rings";
"""


def main():
    if not os.path.exists(PAGE):
        sys.exit("index.html not found - run build/build.py first")
    html = open(PAGE).read()

    start = html.rindex("<script>\n(function(){")
    body = html[start:].split("<script>", 1)[1]
    body = body[:body.rindex("</script>")]

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(STUBS + body + CHECKS)
        path = fh.name
    try:
        run = subprocess.run(["osascript", "-l", "JavaScript", path],
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
