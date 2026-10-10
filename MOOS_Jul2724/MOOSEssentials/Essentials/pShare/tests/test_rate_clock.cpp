#include "Route.h"
#include "MOOS/libMOOS/Utils/MOOSUtilityFunctions.h"

#include <cassert>
#include <chrono>
#include <limits>
#include <string>
#include <thread>

void gates()
{
  for (MOOS::Route::RateClock clock : {MOOS::Route::WALL_TIME, MOOS::Route::MOOS_TIME}) {
    MOOS::Route route;
    route.rate_clock = clock;
    route.frequency = 2.0;
    assert(!route.RateLimited(100)); // first update is immediate
    route.has_sent = true;
    route.last_sent_rate = 100;
    route.has_pending = true;
    assert(route.RateLimited(100.49));
    assert(!route.RateLimited(100.5));
    assert(!route.RateLimited(101));
    assert(route.last_sent_rate == 100); // arrivals cannot extend the deadline
    assert(route.RateLimited(10)); // rebase on backward MOOS clock movement
    assert(route.last_sent_rate == 10);
    assert(route.has_pending); // pending values survive a clock rewind
    assert(route.RateLimited(10.49));
    assert(!route.RateLimited(10.5));
    assert(route.RateLimited(std::numeric_limits<double>::quiet_NaN()));
    route.frequency = 0;
    assert(!route.RateLimited(10)); // unlimited forward ignores the clock
  }
}

void clocks()
{
  MOOS::Route warped, wall;
  assert(warped.rate_clock == MOOS::Route::MOOS_TIME);
  assert(warped.rate_clock_name() == "moos");
  wall.rate_clock = MOOS::Route::WALL_TIME;
  assert(wall.rate_clock_name() == "wall");
  SetMOOSTimeWarp(5);
  const double start_wall = wall.RateNow(), start_moos = warped.RateNow();
  std::this_thread::sleep_for(std::chrono::milliseconds(200));
  const double elapsed_wall = wall.RateNow() - start_wall;
  const double elapsed_moos = warped.RateNow() - start_moos;
  assert(elapsed_wall >= 0.19);
  assert(elapsed_moos / elapsed_wall > 4.8);
  assert(elapsed_moos / elapsed_wall < 5.2);
  SetMOOSTimeWarp(1);
}

void lifetime()
{
  for (MOOS::Route::RateClock clock : {MOOS::Route::WALL_TIME, MOOS::Route::MOOS_TIME}) {
    MOOS::Route route;
    route.rate_clock = clock;
    route.creation_time = 100;
    route.duration_of_share = 10;
    route.max_shares = 2;
    assert(route.IsActive(109));
    assert(!route.IsActive(111)); // duration remains in MOOS time for either clock
    route.duration_of_share = -1;
    route.num_shares_completed = 2;
    assert(!route.IsActive(109)); // share-count policy is unchanged
  }
}

int main(int argc, char **argv)
{
  assert(argc == 2);
  const std::string test = argv[1];
  if (test == "gates") gates();
  else if (test == "clocks") clocks();
  else if (test == "lifetime") lifetime();
  else return 1;
}
