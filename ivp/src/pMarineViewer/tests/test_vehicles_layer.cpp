// Native OpenGL regression: opaque VIEW_POLYGON versus overlapping vehicle.
#include "PMV_Viewer.h"
#include <FL/Fl.H>
#include <FL/gl.h>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

static void require(bool ok, const std::string& message)
{
  if(!ok) {
    std::cerr << "FAIL: " << message << std::endl;
    std::exit(1);
  }
}

static unsigned int redPixels(PMV_Viewer& viewer)
{
  viewer.make_current();
  viewer.draw();
  glFinish();
#ifdef __APPLE__
  const int width = viewer.pixel_w(), height = viewer.pixel_h();
#else
  const int width = viewer.w(), height = viewer.h();
#endif
  std::vector<unsigned char> pixels(width * height * 3);
  glPixelStorei(GL_PACK_ALIGNMENT, 1);
  glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
  require(glGetError() == GL_NO_ERROR, "reading rendered pixels");
  unsigned int count = 0;
  for(unsigned int i=0; i<pixels.size(); i+=3)
    if((pixels[i] > 200) && (pixels[i+1] < 40) && (pixels[i+2] < 40))
      ++count;
  return(count);
}

int main()
{
  PMV_Viewer viewer(0, 0, 400, 400, "Vehicle layer regression");
  require(viewer.getStringInfo("vehicles_layer") == "top", "default top layer");
  require(!viewer.setParam("vehicles_layer", "middle"), "reject invalid layer");
  require(viewer.getStringInfo("vehicles_layer") == "top", "invalid preserves layer");
  require(viewer.initGeodesy(42, -71), "geodesy");
  viewer.updateMOOSGeodesy();
  require(viewer.setParam("tiff_file", "null.tif"), "no background image needed");
  viewer.setParam("tiff_viewable", "false");
  viewer.setParam("hash_viewable", "false");
  viewer.setParam("datum_viewable", "false");
  viewer.setParam("vehicles_name_mode", "off");
  viewer.setParam("trails_viewable", "false");
  viewer.setParam("curr_time", 1.0);
  std::string reason;
  require(viewer.handleNodeReport("NAME=test,TYPE=circle,X=80,Y=0,SPD=0,HDG=0,"
                                 "LENGTH=50,TIME=0.5,COLOR=red", reason), reason);
  require(viewer.handleNodeReport("NAME=test,TYPE=circle,X=0,Y=0,SPD=0,HDG=0,"
                                 "LENGTH=50,TIME=1,COLOR=red", reason), reason);
  require(viewer.addGeoShape("VIEW_POLYGON",
                            "pts={-1000,-1000:1000,-1000:1000,1000:-1000,1000},"
                            "label=overlay,fill_color=green,fill_transparency=1,"
                            "edge_color=invisible,vertex_size=0,label_color=invisible",
                            "shoreside"), "overlay polygon");
  viewer.setConfigComplete();
  viewer.show();
  Fl::check();
  viewer.setCtrView(0, 0);
  const unsigned int top = redPixels(viewer);
  require(top > 10, "default vehicle drawn above polygon");
  viewer.setParam("trails_color", "red");
  viewer.setParam("trails_point_size", 5.0);
  viewer.setParam("trails_viewable", "true");
  const unsigned int with_trail = redPixels(viewer);
  require(with_trail > top, "trail drawn above polygon in top layer");
  require(viewer.setParam(" Vehicles_Layer ", " BOTTOM "), "normalized bottom setting");
  require(viewer.getStringInfo("vehicles_layer") == "bottom", "bottom query");
  require(redPixels(viewer) == 0, "polygon covers bottom-layer vehicle and trail");
  require(!viewer.setParam("vehicles_layer", ""), "reject empty layer");
  require(viewer.getStringInfo("vehicles_layer") == "bottom", "invalid preserves bottom");
  require(viewer.setParam("vehicles_layer", "top"), "restore top");
  require(redPixels(viewer) == with_trail, "restored vehicle/trail drawn exactly once");
  viewer.setParam("trails_viewable", "false");
  require(redPixels(viewer) == top, "independent trail visibility");
  require(viewer.setParam("vehicles_viewable", "false"), "hide vehicles");
  require(redPixels(viewer) == 0, "hidden vehicles remain hidden");
  viewer.hide();
  std::cout << "PASS: default/top, bottom, invalid values, switching and visibility" << std::endl;
  return(0);
}
