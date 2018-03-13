#include "simulator.h"
#include "cylinders.h"
#include <stdlib.h>


#define LEN 21


double bias = -0.0025;
double thresh = 0.01;
double hthresh = 1.;


void init_mapper() {
  char *bstr = getenv("MAP_BIAS");
  char *tstr = getenv("MAP_THRESH");
  char *htstr = getenv("MAP_HTHRESH");

  if (bstr) bias = atof(bstr);
  if (tstr) thresh = atof(tstr);
  if (htstr) hthresh = atof(htstr);
}



static int small;
void map_state_array(double *x) {
  int i;

  small = 1;
  for (i=0; i<LEN; i++) {
    if (x[i] + bias > thresh) {
      set_vcyl(i, 1);
      small = 0;
      //      printf("%d +\n", i);
    } else if (x[i] + bias < -thresh) {
      set_vcyl(i, -1);
      small = 0;
      //      printf("%d -\n", i);
    } else {
      set_vcyl(i, 0);
    }
  }
}


int vstate_small() {
  return small;
}


void map_hstate(double h) {
  if (h > hthresh) {
    horiz(1, 1);
  } else if (h < -hthresh) {
    horiz(-1, 1);
  } else {
    horiz(0, 0);
  }
}
