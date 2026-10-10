/*
 * Route.cpp
 *
 *  Created on: Sep 1, 2012
 *      Author: pnewman
 */

#include <sstream>
#include <iostream>
#include <chrono>
#include <cmath>

#include "MOOS/libMOOS/Utils/MOOSUtilityFunctions.h"
#include "Route.h"

namespace MOOS {

Route::Route() {
    last_time_sent = 0.0;
    frequency   = 0.0;
    behavior = FORWARD;
    rate_clock = MOOS_TIME;
    has_sent = false;
    last_sent_rate = 0.0;
    has_pending = false;
	duration_of_share = -1.0; 
	max_shares = 0;
	num_shares_completed = 0;
	creation_time = Time();
}

Route::~Route() {
	// TODO Auto-generated destructor stub
}


bool Route::IsActive(const double time_now){

	//special duration=0 share
	if(duration_of_share==0.0 && num_shares_completed < max_shares){
		return true;
	}

	//has the allowable share window passed?
	//if <0 then no limit has been set;	
	if(duration_of_share >=0.0 && time_now-creation_time > duration_of_share){
		return false;
	}

	//has the maximum number of shares been exceeded?
	//if <0 then no limit has been set;
	if(max_shares >=0 && num_shares_completed>=max_shares){
		return false;
	}

	// Rate behavior is applied by pShare, independently of route lifetime.
	return true;
}

double Route::RateNow() const
{
	return rate_clock == MOOS_TIME ? MOOS::Time() :
		std::chrono::duration<double>(
			std::chrono::steady_clock::now().time_since_epoch()).count();
}

bool Route::RateLimited(double now)
{
	if(!has_sent || frequency <= 0.0)
		return false;
	if(!std::isfinite(now))
		return true;
	// A MOOS clock rewind must not hold pending data until the old epoch.
	// Restart only the rate interval; preserve pending data and lifetime rules.
	if(now < last_sent_rate)
		last_sent_rate = now;
	return now - last_sent_rate < 1.0/frequency;
}

std::string Route::rate_clock_name() const
{
	return rate_clock == MOOS_TIME ? "moos" : "wall";
}

std::string Route::behavior_name() const
{
	return behavior == FORWARD ? "forward" : behavior == DROP ? "drop" :
		behavior == COALESCE ? "coalesce" : "latest";
}

std::string Route::to_string() const
{
	std::stringstream ss;
	ss<<"ShareInfo:\n"
			<<"add: "<<dest_address.to_string()<<std::endl
			<<"dest_name: "<<dest_name<<std::endl
			<<"src_name : "<<src_name<<std::endl
			<<"multicast: "<<multicast<<std::endl
	        <<"frequency: "<<frequency<<std::endl
	        <<"behavior : "<<behavior_name()<<std::endl
	        <<"rate clock: "<<rate_clock_name()<<std::endl
			<<"duration : "<<duration_of_share<<std::endl
			<<"maxshares: "<<max_shares<<std::endl;
			
	return ss.str();
}

bool Route::operator==(const Route & r) const
{
	return r.dest_address.port()==dest_address.port() &&
			r.dest_address.host()==dest_address.host() &&
		r.dest_name == dest_name &&
		r.src_name==  src_name &&
		r.multicast == multicast;
}


}
