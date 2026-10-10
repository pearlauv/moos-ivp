/*
 * Route.h
 *
 *  Created on: Sep 1, 2012
 *      Author: pnewman
 */

#ifndef ROUTE_H_
#define ROUTE_H_

/*
 *
 */

#include "MOOS/libMOOS/Utils/IPV4Address.h"
#include <string>
#include <vector>
#include "MOOS/libMOOS/Comms/MOOSMsg.h"

namespace MOOS {

class Route {
public:
	Route();
	virtual ~Route();
	bool IsActive(const double time_now);
	enum Behavior { FORWARD, DROP, COALESCE, LATEST };
	enum RateClock { WALL_TIME, MOOS_TIME };
	double RateNow() const;
	bool RateLimited(double now);
	std::string rate_clock_name() const;

	bool operator==(const Route & r) const;
	MOOS::IPV4Address dest_address;
	std::string dest_name;
	std::string src_name;
	bool multicast;
	std::string to_string() const;
	std::string behavior_name() const;
	double frequency;
	Behavior behavior;
	RateClock rate_clock;
	bool has_sent;
	double last_sent_rate;
	std::vector<unsigned char> last_payload;
	bool has_pending;
	CMOOSMsg pending_message;
	double last_time_sent;
	double duration_of_share;
	double creation_time;
	unsigned int num_shares_completed;
	unsigned int max_shares;

};

}

#endif /* ROUTE_H_ */
