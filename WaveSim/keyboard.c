#include "cylinders.h"
#include "io.h"
#include <stdio.h>
#include <termios.h>
#include <unistd.h>
#include <stdlib.h>


#define LEN 21


struct termios old;
struct termios new;

void makeraw() {
  tcgetattr(0, &old);
  tcgetattr(0, &new);
  cfmakeraw(&new);
  tcsetattr(0, TCSANOW, &new);
}


void makecooked() {
  tcsetattr(0, TCSANOW, &old);
}



void msleep(int msec) {
  usleep(msec * 1000);
}

void allup() {
  int i;
  for(i=0;i<LEN;i++) {
    set_vcyl(i, 1);
    msleep(50);
  }
}

void alldown() {
  int i;
  for(i=0;i<LEN;i++) {
    set_vcyl(i, -1);
    msleep(50);
  }
}

void allstop() {
  int i;
  for(i=0;i<LEN;i++) set_vcyl(i, 0);
}


void cycle_power() {
  static int state=0;
  state ++;
  state %= 3;
  switch (state) {
  case 0:
    power_off();
    pump_off();
    break;
  case 1:
    power_on();
    pump_off();
    break;
  case 2:
    power_on();
    pump_on();
    break;
  }
}


int main(int argc, char *argv[]) {
  unsigned short c;

  printf("hit 'a' through 'u' to activate verticals\n");
  printf("hit '1' through '3' to activate horizontal\n");
  printf("hit '8' through '0' to activate all\n");
  printf("spacebar cycles through pump states\n");
  printf("hit 'esc' to quit\n");

  setup_io();

  makeraw();

  while(1) {
    c = getchar();
    if (c == 27) {
      makecooked();
      exit(0);
    }
    if (c >= 'a' && c <= 'u') {
      c -= 'a';
      printf("%d\r\n", c);
      msleep(100);
      set_vcyl(c, 1);
      msleep(500);
      set_vcyl(c, 0);
      msleep(100);
      set_vcyl(c, -1);
      msleep(500);
      set_vcyl(c, 0);
    }
    if (c == '1') {
      horiz(-1, 1);
    }
    if (c == '2') {
      horiz(0, 0);
    }
    if (c == '3') {
      horiz(1, 1);
    }
    if (c == '8') {
      allup();
    }
    if (c == '9') {
      allstop();
    }
    if (c == '0') {
      alldown();
    }
    if (c == ' ') {
      cycle_power();
    }
  }
  
  close_io();
}
