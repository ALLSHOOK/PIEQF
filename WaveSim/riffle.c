#include "cylinders.h"
#include "io.h"


void msleep(int msec) {
  usleep(msec * 1000);
}


// Sequential Order of HV1-21 floor pieces lifting with a half second delay between each
void riffle_vertical(void) {
  int i;

  for (i = 0; i<21; i++) {
    // pulse cylinder i
    msleep(20);
    set_vcyl(i, 1);
  }
  msleep(1000);
  for (i=0; i<21; i++) {
    msleep(20);
    set_vcyl(i, -1);
  }
  msleep(1000);
  for (i=0; i<21; i++) {
    set_vcyl(i, 0);
  }
}


void test_others(void) {
  // drive right full
  horiz(1, 0xffff);
  msleep(2000);
  // reset to center
  horiz(0, 0);
  msleep(2000);
  // drive left full
  horiz(-1, 0xffff);
  msleep(2000);
  // reset to center
  horiz(0, 0);
  msleep(100);

    pump_on();
    msleep(500);
    pump_off();
    msleep(500);

    power_on();
    msleep(500);
    power_off();
    msleep(500);
}


void group1(int x, int y, int z) {
  set_vcyl(6, 1); set_vcyl(7, 1); set_vcyl(8, 1); set_vcyl(9, 1); set_vcyl(10, 1); set_vcyl(11, 1); set_vcyl(12, 1);
  msleep(y);
  set_vcyl(6, 0); set_vcyl(7, 0); set_vcyl(8, 0); set_vcyl(9, 0); set_vcyl(10, 0); set_vcyl(11, 0); set_vcyl(12, 0);
  msleep(x);
}

  


int main(int argc, char *argv[]) {
  setup_io();
  
  riffle_vertical();
  //test_others();
  close_io();
}
