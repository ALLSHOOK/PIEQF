#include <stdio.h>
#include <fcntl.h>
#include <stdlib.h>
#include <signal.h>
#include <assert.h>


#include "simulator.h"
#include "mapper.h"


static int coffee = 0;
static int verbose = 1;


#define GS_SLEEP 0
#define GS_BREATHE 1
#define GS_ACTIVE 2
#define GS_RIPPLE 3
static int global_state = 0;

#define DS_DUMP 0
#define DS_NODUMP 1
static int dump_state = 0;

#define LS_NORMAL 0
#define LS_LOCKOUT 1
static int lockout_state = 0;

static int statecount = 0;

#define LEN 21


double x[LEN];
double h;


int vpipe_fd;
int hpipe_fd;
char msg[80];
int msglen;


void set_ls(int state) {
  switch(state) {
  case LS_NORMAL:
    if (verbose && (lockout_state != LS_NORMAL)) printf("  unlocking verticals\n");
    lockout_state = LS_NORMAL;
    return;
  case LS_LOCKOUT:
    if (verbose && (lockout_state != LS_LOCKOUT)) printf("  locking out verticals\n");
    lockout_state = LS_LOCKOUT;
    return;
  }
}




void set_ds(int state) {
  switch(state) {
  case DS_DUMP:
    if (verbose && (dump_state != DS_DUMP)) printf("  dumping\n");
    pump_off();
    dump_state = DS_DUMP;
    return;
  case DS_NODUMP:
    if (verbose && (dump_state != DS_NODUMP)) printf("  closing dump valve!!\n");
    pump_on();
    dump_state = DS_NODUMP;
    return;
  }
}



void set_gs(int state) {
  if (global_state == state) return;
  switch(state) {
  case GS_SLEEP:
    if (verbose) printf("  global state going to SLEEP\n");
    set_ds(DS_DUMP);
    set_ls(LS_NORMAL);
    power_off();
    statecount = 0;
    global_state = GS_SLEEP;
    return;
  case GS_BREATHE:
    if (verbose) printf("  global state going to BREATHE\n");
    set_ds(DS_DUMP);
    set_ls(LS_NORMAL);
    power_on();
    usleep(1000000);
    statecount = 0;
    global_state = GS_BREATHE;
    return;
  case GS_ACTIVE:
    if (verbose) printf("  global state going to ACTIVE\n");
    set_ds(DS_NODUMP);
    set_ls(LS_LOCKOUT);
    power_on();
    statecount = 0;
    global_state = GS_ACTIVE;
    return;
  case GS_RIPPLE:
    if (verbose) printf("  global state going to RIPPLE\n");
    set_ds(DS_DUMP);
    set_ls(LS_NORMAL);
    power_on();
    statecount = 0;
    global_state = GS_RIPPLE;
    return;
  }
}


int check_for_input(int hflag, int vflag) {
  char *p = msg;

  msglen = 0;

  if (hflag) {
    while ((read(hpipe_fd, p, 1) == 1) && (*p++ != '\n')) msglen++;

    if (msglen > 0) {
      msg[msglen] = '\0';
      if (verbose >= 2) {
	printf("got %s\n", msg);
      }
      return 1;
    }
  }

  if (vflag) {
    while ((read(vpipe_fd, p, 1) == 1) && (*p++ != '\n')) msglen++;
    
    if (msglen > 0) {
      msg[msglen] = '\0';
      if (verbose >= 2) {
	printf("got %s\n", msg);
      }
      return 1;
    }
  }
  
  return 0;
}
  

static int MAG_THRESH = 10;
void do_input() {
  int chan, mag, dur;

  if (msg[0] == 'C') {
    sscanf(msg, "C%dM%dD%d\n", &chan, &mag, &dur);
    if (verbose) {
      printf("chan %d mag %d dur %d\n", chan, mag, dur); 
    }
    if ((global_state == GS_BREATHE) && (chan != 99)) {
      if (mag < MAG_THRESH) {
	if (verbose) {
	  printf("   ignoring...\n");
	}
	return;
      }
    }

    switch (chan) {
    case 0:   // north
      if (lockout_state == LS_LOCKOUT) break;
      set_gs(GS_RIPPLE);
      sim_drop_pebble(19, mag / 10.0);
      break;
    case 1:   // south
      if (lockout_state == LS_LOCKOUT) break;
      set_gs(GS_RIPPLE);
      sim_drop_pebble(1, mag / 10.0);
      break;
    case 2:   // east
    case 3:   // west
      if (lockout_state == LS_LOCKOUT) break;
      set_gs(GS_RIPPLE);
      sim_drop_pebble(10, mag / 10.0);
      break;
    case 99:  // earthquake!!
      if (verbose) printf("EARTHQUAKE!!\n");
      set_gs(GS_ACTIVE);
      set_ds(DS_NODUMP);
      set_ls(LS_LOCKOUT);
      sim_tickle_horiz(mag);
      break;
    }
  }
}


static int breathe_time = 70;
static int pause_time = 900;

void breathe_process() {
  static int vindex = 0;
  static int count = 0;
  static int dir = 0;
  static int nextdir = 1;

  count++;
  switch (dir) {
  case 1:
  case -1:
    if (count >= breathe_time) {
      count = 0;
      nextdir = -dir;
      dir = 0;
      horiz(0, 0);
      set_vcyl(vindex, 0);
      vindex++;
      vindex %= LEN;
    }
    return;
  case 0:
    if (count >= pause_time) {
      count = 0;
      dir = nextdir;
      horiz(dir, 1);
      set_vcyl(vindex, -1);
    }
    return;
  }
}



void handle_usr1(int foo) {
  coffee = 1;
}


void handle_usr2(int foo) {
  coffee = 0;
}


main(int argc, char *argv[]) {
  char *vpipename;
  char *hpipename;

  vpipename = getenv("VPIPE_NAME");
  if (!vpipename) vpipename = "/tmp/pieqf-vert.fifo";
  vpipe_fd = open(vpipename, O_RDONLY);
  if (fcntl(vpipe_fd, F_SETFL, O_NONBLOCK)) perror("fcntl");

  hpipename = getenv("HPIPE_NAME");
  if (!hpipename) hpipename = "/tmp/pieqf-hori.fifo";
  hpipe_fd = open(hpipename, O_RDONLY);
  if (fcntl(hpipe_fd, F_SETFL, O_NONBLOCK)) perror("fcntl");

  signal(SIGUSR1, handle_usr1);
  signal(SIGUSR2, handle_usr2);

  char *breathetime = getenv("BREATHE_TIME");
  if (breathetime) breathe_time = atoi(breathetime);
  char *pausetime = getenv("PAUSE_TIME");
  if (pausetime) pause_time = atoi(pausetime);

  setup_io();
  init_mapper();
  sim_init();

  while (1) {
    switch (global_state) {
    case GS_SLEEP:
      // check for wake up
      if (coffee) {
	// wake up
	if (verbose) {
	  printf("waking up...\n");
	}
	set_gs(GS_BREATHE);
      }
      break;

    case GS_BREATHE:
      breathe_process();
      if (check_for_input(1, 1)) do_input();

      // check for go to sleep
      if (!coffee) {   // time to go to sleep
	if (verbose) {
	  printf("going to sleep...\n");
	}
	set_gs(GS_SLEEP);
      }
      break;

    case GS_ACTIVE:
      sim_update();
      sim_getstate(x);
      map_state_array(x);

      sim_gethstate(&h);
      map_hstate(h);
      if (hstate_small()) {
	if (verbose) {
	  printf("h state is small...\n");
	}
	set_gs(GS_RIPPLE);
      }
      break;

    case GS_RIPPLE:
      if (check_for_input(0, 1)) do_input();
      sim_update();
      sim_getstate(x);
      map_state_array(x);

      sim_gethstate(&h);
      map_hstate(h);
      if (hstate_verysmall() && vstate_small()) {
	if (verbose) {
	  printf("v state is small...\n");
	}
	set_gs(GS_BREATHE);
      }
      break;
    }
    usleep(5000);
    statecount++;
  }
}
