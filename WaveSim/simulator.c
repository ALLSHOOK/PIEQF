#include <stdio.h>
#include <math.h>
#include <stdlib.h>


#define LEN 21

static double c2 = 0.1;  // square velocity
static double d = 0.1;   // vertical damping coefficient
static double dt = 0.1;  // everything integration time
static double hf2 = 0.1; //
static double hd = 0.02; // horizontal damping
static double hsmall = 3.0; //horizontal energy
static double hverysmall = 0.5; //before breathing state

double x[LEN];          // source array
double xdot[LEN];
double y[LEN];          // destination array
double ydot[LEN];

double h, hdot;


void zero(double *x) {
  int i;
  for (i=0; i<LEN; i++) x[i] = 0.;
}


void sim_drop_pebble(int position, double energy) {
  x[position] = energy;
}


void sim_tickle_horiz(double energy) {
  h = energy;
}


double h_energy() {
  return hf2 * h * h + hdot * hdot;
}

  
int hstate_small() {
  double tmp;

  tmp = h_energy();
  if (tmp < hsmall) return 1;
  return 0;
}


int hstate_verysmall() {
  double tmp;

  tmp = h_energy();
  if (tmp < hverysmall) return 1;
  return 0;
}


void print(double *x) {
  int i;
  for (i=0; i<LEN; i++) {
    printf("%0.1f ", x[i]);
  }
  printf("\n");
  fflush(stdout);
}


void copy() {
  int i;
  for (i=0; i<LEN; i++) {
    x[i] = y[i];
    xdot[i] = ydot[i];
  }
}


double laplacian(double *x) {
  return (*(x+1) - *(x)) - (*(x) - *(x-1));
}


void sim_update() {
  int i;
  double h2, hdot2;

  // xxx fix boundary conditions!
  // vertical
  //   integrate
  for (i=1; i<LEN-1; i++) {
    ydot[i] = xdot[i] + dt * (c2 * laplacian(&x[i]) - d * xdot[i]);
  }
  for (i=0; i<LEN; i++) {
    y[i] = x[i] + dt * xdot[i];
  }
  //   propagate
  copy();
#ifdef DEBUG_SIM
  print(x);
#endif

  // horizontal
  //   integrate
  hdot2 = hdot + dt * (-hf2 * h - hd * hdot);
  h2 = h + dt * hdot;
  //   propagate
  hdot = hdot2;
  h = h2;
}


void sim_getstate(double *out) {
  int i;
  for (i=0; i<LEN; i++) {
    out[i] = x[i];
  }
}



double sim_gethstate() {
  return h;
}

  
void sim_init() {
  char *env_c2 = getenv("SIM_C2");
  char *env_d = getenv("SIM_DAMPING");
  char *env_dt = getenv("SIM_DT");
  char *env_hd = getenv("SIM_HD");
  char *env_hf2 = getenv("SIM_HF2");
  char *env_hsmall = getenv("SIM_HSMALL");

  if (env_c2) c2 = atof(env_c2);
  if (env_d) d = atof(env_d);
  if (env_dt) dt = atof(env_dt);
  if (env_hd) hd = atof(env_hd);
  if (env_hf2) hf2 = atof(env_hf2);
  if (env_hsmall) hsmall = atof(env_hsmall);

  fprintf(stderr, "c2=%lf d=%lf dt=%lf hf2=%lf hd=%lf hsmall=%lf hvsmall=%lf\n", c2, d, dt, hf2, hd, hsmall, hverysmall);

  zero(x);
  zero(xdot);
  zero(y);
  zero(ydot);

  h = hdot = 0.;
}
