#include "io.h"


struct cylinder {
	int outword;
	int outbit;
	int inword;
	int inbit;
};



struct cylinder vcylinder_list[] = {
	{ 0, 0, 0, 1 },	// 1a 1b
	{ 0, 2, 0, 3 }, // 2a 2b 
	{ 0, 4, 0, 5 }, // 3a 3b
	{ 0, 6, 0, 7 }, // 4a 4b
	{ 1, 0, 1, 1 },   // 5a 5b
	{ 1, 2, 1, 3 },   // 6a 6b
	{ 1, 4, 1, 5 },   // 7a 7b
	{ 1, 6, 1, 7 },   // 8a 8b
	{ 2, 0, 2, 1 },   // 9a 9b
	{ 2, 2, 2, 3 }, // 10a 10b

	{ 2, 4, 2, 5 }, // 11a 11b
	{ 2, 6, 2, 7 }, // 12a 12b
	{ 3, 0, 3, 1 },   // 13a 13b
	{ 3, 2, 3, 3 },   // 14a 14b
	{ 3, 4, 3, 5 },   // 15a 15b
	{ 3, 6, 3, 7 },   // 16a 16b

	{ 4, 0, 4, 1 },   // 17a 17b
	{ 4, 2, 4, 3 }, // 18a 18a
	{ 4, 4, 4, 5 }, // 19a 19b
	{ 4, 6, 4, 7 }, // 20a 20b
	{ 5, 0, 5, 1}     // 21a 21b
};


void set_vcyl(int cylnum, int state) {   // +1 for out, 0 for stop, -1 for retract
	int wordnum, bitnum;
	
	struct cylinder c = vcylinder_list[cylnum];
	
	if (state == 1) {     // out
		clr_o(c.inword, c.inbit);
		set_o(c.outword, c.outbit);
		return;
	}
	if (state == -1) {            // in
	  clr_o(c.outword, c.outbit);
		set_o(c.inword, c.inbit);
		return;
	}
	if (state == 0) {
		clr_o(c.inword, c.inbit);
		clr_o(c.outword, c.outbit);
		return;
	}
}


void pump_on() {
  set_o(5, 6);
}

void pump_off() {
  clr_o(5, 6);
}

void power_on() {
  set_o(5, 7);
}

void power_off() {
  clr_o(5, 7);
}

void air_on() {
  set_o(5, 4);
}

void air_off() {
  clr_o(5, 4);
}

void spare_on() {
  set_o(5, 5);
}

void spare_off() {
  clr_o(5, 5);
}

// horiz(dir, mag)
// dir: +1 is right, 0 is stop, -1 is left
// mag: ignored if (dir==0), else (0...0xffff), applied to
//   chosen direction.
// Return: 0 on success, nonzero on any error.
// Note: 'mag' scale is unsigned short (16 bits) because that
//   exactly matches that DAC resolution.
#if 0
int horiz(int dir, unsigned short mag) {
  // wiring/mapping notes:
  // DIO output (5,2) "horiz1a" is used to enable/disable
  // solenoid drive.  current logic is 0=disable, 1=enable.
  // DAC outputs 0 and 1 are used to drive the 2 proportional
  // valves.  current mapping is 0=right, 1=left.
  // to alter either of those in software, change it HERE ONLY.

  int dirfd_on = -1 ;
  int dirfd_off = -1 ;

  if (0 == dir) {
    // stop command:
    // clear the output enable bit (digital), AND
    // then reset both analog outputs to zero.
    clr_o(5, 2);
    set_analog(0, 0);
    set_analog(1, 0);
    return 0;
  }

  // not a stop command.  map the dir to the dirfd, or
  // fail now if invalid.
  if (1 == dir) {
    // "right" == (drive dac-fd 0 and not 1)
    dirfd_on = 0;
    dirfd_off = 1;
  } else if (-1 == dir) {
    // "left" == (drive dac-fd 1 and not 0)
    dirfd_on = 1;
    dirfd_off = 0;
  } else {
    // invalid
    return -1;
  }

  // drive the requested direction and zero the other.
  set_analog(dirfd_on, mag);
  set_analog(dirfd_off, 0);
  update_analog();

  // enable drive (if not already enabled, else harmless)
  set_o(5, 2);
}

#else

horiz(int dir, unsigned short mag) {
  switch (dir) {
  case -1:
    clr_o(5, 3);
    set_o(5, 2);
    break;
  case 0:
    clr_o(5, 2);
    clr_o(5, 3);
    break;
  case 1:
    clr_o(5, 2);
    set_o(5, 3);
    break;
  }
}
#endif
