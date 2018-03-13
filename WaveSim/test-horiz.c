#include "cylinders.h"
#include "io.h"

#include <stdio.h>


void msleep(int msec) {
  usleep(msec * 1000);
}


int main(int argc, char *argv[]) {
  int pwrstate = 0;

  setup_io();

  if (argc > 1) pwrstate = atoi(argv[1]);

  if (pwrstate) power_on();
  if (pwrstate > 1) pump_on();
  msleep(1000);
  
  horiz(1, 1);
  msleep(2000);
  horiz(-1,1);
  msleep(2000);
  horiz(0, 0);

  pump_off();
  power_off();
  close_io();
}
