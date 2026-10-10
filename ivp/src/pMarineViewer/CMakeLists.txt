#--------------------------------------------------------
# The CMakeLists.txt for:                   pMarineViewer
# Author(s):                                Mike Benjamin
#--------------------------------------------------------

# Set System Specific Libraries
if (${WIN32})
  SET(SYSTEM_LIBS wsock32)
else (${WIN32})
  SET(SYSTEM_LIBS m)
endif (${WIN32})

if(CMAKE_SYSTEM_NAME STREQUAL Linux)
  SET(SYSTEM_LIBS ${SYSTEM_LIBS} GL)
endif(CMAKE_SYSTEM_NAME STREQUAL Linux)

FILE(GLOB SRC *.cpp)

If (${APPLE})
      # If you want to create an Apple BUNDLE, do it here
      ADD_EXECUTABLE(pMarineViewer ${SRC})
ELSE (${APPLE})
      ADD_EXECUTABLE(pMarineViewer ${SRC})
ENDIF (${APPLE})
      
TARGET_LINK_LIBRARIES(pMarineViewer         
  ${MOOS_LIBRARIES}
  ${MOOSGeodesy_LIBRARIES}
  ${SYSTEM_LIBS}
  genutil
  marineview
  geodaid
  contacts
  geometry
  ucommand
  realm
  apputil
  mbutil
  bhvutil
  # Standard libraries used by this project's FLTK apps...
  fltk 
  fltk_gl 
  dl
  tiff)

# http://developer.apple.com/qa/qa2007/qa1567.html
IF (${APPLE})
  SET_TARGET_PROPERTIES(pMarineViewer PROPERTIES	  
    LINK_FLAGS "-framework OpenGL -framework Cocoa"
    )
  SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-cast-function-type ")
  SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-deprecated-declarations ")
ENDIF (${APPLE})

ADD_TEST(MyTest1 ${EXECUTABLE_OUTPUT_PATH}/pMarineViewer --version)

# Opt-in native rendering regression; requires an OpenGL display (or Xvfb).
ADD_EXECUTABLE(test_pMarineViewer_layers EXCLUDE_FROM_ALL
  tests/test_vehicles_layer.cpp PMV_Viewer.cpp)
TARGET_INCLUDE_DIRECTORIES(test_pMarineViewer_layers PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
GET_TARGET_PROPERTY(PMV_TEST_LIBS pMarineViewer LINK_LIBRARIES)
TARGET_LINK_LIBRARIES(test_pMarineViewer_layers ${PMV_TEST_LIBS})
IF (${APPLE})
  SET_TARGET_PROPERTIES(test_pMarineViewer_layers PROPERTIES
    LINK_FLAGS "-framework OpenGL -framework Cocoa")
ENDIF (${APPLE})

