#include <stdio.h>
#include <math.h>
#include <fcntl.h>


#define LEN 21

static double k = 0.1;  // diffusion coefficient

double x[LEN];          // source array
double y[LEN];          // destination array


int pipe_fd;


void zero(double *x) {
  int i;
  for (i=0; i<LEN; i++) x[i] = 0.;
}


void drop_pebble(double *x) {
  x[10] = 1.0;
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
  }
}


double update_cell(double a, double b, double c) {
  double bdotdot;

  bdotdot = (c - b) - (b - a);
  return b + k * bdotdot;
}


void update() {
  int i;
  for (i=1; i<LEN-1; i++) {
    y[i] = update_cell(x[i-1], x[i], x[i+1]);
  }
}


int check_for_input() {
  char msg[80];
  int n;

  n = read(pipe_fd, msg, 80);
  if (n > 0) {
    // your message is in buf; interpret it wisely
    // ...
    printf("got %s\n", msg);
    fflush(stdout);
    return 1;
  }
  return 0;
}
  
  
main(int argc, char *argv[]) {
  pipe_fd = open("my_pipe", O_RDONLY);
  if (fcntl(pipe_fd, F_SETFL, O_NONBLOCK)) perror("fcntl");

  zero(x);
  zero(y);

  while (1) {
    if (check_for_input()) drop_pebble(x);

    update();
    copy();
    print(x);  // write result to machine
    usleep(500000);
  }
}
