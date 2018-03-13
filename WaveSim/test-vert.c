#include "cylinders.h"
#include "io.h"

#include <stdio.h>


void msleep(int msec) {
  usleep(msec * 1000);
}


// Sequential Order of HV1-21 floor pieces lifting with a half second delay between each
void riffle_vertical(void) {
  int i;

  for (i = 0; i<21; i++) {
    // pulse cylinder i
    printf("%d\n", i);
    msleep(100);
    set_vcyl(i, 1);
    msleep(500);
    set_vcyl(i, 0);
    msleep(100);
    set_vcyl(i, -1);
    msleep(500);
    set_vcyl(i, 0);
  }
}


int main(int argc, char *argv[]) {
  int pwrstate = 0;

  setup_io();

  if (argc > 1) pwrstate = atoi(argv[1]);

  if (pwrstate) power_on();
  if (pwrstate > 1) pump_on();
  msleep(1000);
  riffle_vertical();
  power_off();
  pump_off();
  close_io();
}
