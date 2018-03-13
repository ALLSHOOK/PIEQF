/***************************************************************************
 *
 *  all_outputs.c
 *
 *  This program is used to test the PCI-DDA02/16 outputs on on ports.
 *  A mix of Warren Jaspers test_dda0X-1.6.c and Curt Wuollet's smio.c
 *  Linux loadable module(pci-dda0X_16).
 *
 ***************************************************************************/

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include "pci-dda0X-16.h"	/* Changed from dio.h */
#include "io.h"

// XXX FIXME
// unchecked strcpy into this string is done below.
// be careful not to overrun (again).
char DevNameIO[200];

int fd_dac[2];
int fd_dio[6];
unsigned char values[6];

// setup_io:
// Open all io fds to be used, setting defaults and filling fd tables.
// Exit program if anything fails.
// Currently we fill fd_dac[] with fds for 2 DACs and
// fd_dio[] with fds for 6 DIOs.
void setup_io(void) {
  /* open/setup the two DAC fds */
  strcpy(DevNameIO, "/dev/dda0x-16/da0_0");
  if ((fd_dac[0] = open(DevNameIO, O_RDWR )) < 0) {
    perror("DevNameIO");
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }
  strcpy(DevNameIO, "/dev/dda0x-16/da0_1");
  if ((fd_dac[1] = open(DevNameIO, O_RDWR )) < 0) {
    perror("DevNameIO");
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  // Default DAC gains.
  // "UP_10_0V" means (0V...+10V) which is what we want.
  // Just set it here and do not provide support for changing it.
  ioctl(fd_dac[0], DAC_SET_GAINS, UP_10_0V);
  ioctl(fd_dac[1], DAC_SET_GAINS, UP_10_0V);

  // Enable simultaneous DAC updates.
  // This is what we want.  But the implication is that the user
  // of this code must make a separate call for update after setting
  // all values.
  ioctl(fd_dac[0], DAC_SET_SIMULT, 1);
  ioctl(fd_dac[1], DAC_SET_SIMULT, 1);

  /* open/setup the 6 DIO fds */
  strcpy(DevNameIO, "/dev/dda0x-16/dio0_0A");
  if ((fd_dio[0] = open(DevNameIO, O_RDWR )) < 0) {
    perror("DevNameIO");
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }
  strcpy(DevNameIO, "/dev/dda0x-16/dio0_0B");
  if ((fd_dio[1] = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }
  strcpy(DevNameIO, "/dev/dda0x-16/dio0_0C");
  if ((fd_dio[2] = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  strcpy(DevNameIO, "/dev/dda0x-16/dio0_1A");
  if ((fd_dio[3] = open(DevNameIO, O_RDWR )) < 0) {
    perror("DevNameIO");
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  strcpy(DevNameIO, "/dev/dda0x-16/dio0_1B");
  if ((fd_dio[4] = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  strcpy(DevNameIO, "/dev/dda0x-16/dio0_1C");
  if ((fd_dio[5] = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  ioctl(fd_dio[0], DIO_SET_DIRECTION, 0);
  ioctl(fd_dio[1], DIO_SET_DIRECTION, 0);
  ioctl(fd_dio[2], DIO_SET_DIRECTION, 0);
  ioctl(fd_dio[3], DIO_SET_DIRECTION, 0);
  ioctl(fd_dio[4], DIO_SET_DIRECTION, 0);
  ioctl(fd_dio[5], DIO_SET_DIRECTION, 0);
}


void close_io(void) {
  close(fd_dac[0]);
  close(fd_dac[1]);
  close(fd_dio[0]);
  close(fd_dio[1]);
  close(fd_dio[2]);
  close(fd_dio[3]);
  close(fd_dio[4]);
  close(fd_dio[5]);
}


// set_o(reg, bit):
// Set the digital output at register 'reg' and bit 'bit'.
int set_o(short reg, short bit) {
  unsigned char value;

  if ((reg < 0) || (reg > 5))
    return -1;

  value = values[reg];
  value = value | (1 << bit);
  values[reg] = value;
  write(fd_dio[reg], &value, 1);
  return 0;
}


// clr_o(reg, bit):
// Clear the digital output at register 'reg' and bit 'bit'.
int clr_o(short reg, short bit) {
  unsigned char value;

  if ((reg < 0) || (reg > 5))
    return -1;

  value = values[reg];
  value = value & ~(1 << bit);
  values[reg] = value;
  write(fd_dio[reg], &value, 1);
  return 0;
}

// To set analog outputs...
//
// interface: first call set_analog on all dac ports you want to
// set new values for, then call update_analog to update all the
// physical voltage outputs simultaneously.

// set_analog(unsigned char port, unsigned short val):
// Set the value of an analog output.
// Note, value is an unsigned short, which is 16 bits,
// range from 0 - 0xffff.  Meaning depends on DAC gain
// setting but for unipolar (positive voltages only) mode,
// it is simply linear to the full scale of voltage from 0V
// to +VFullScale.
// Return 0 on success, nonzero on any error.
int set_analog(int dacport, unsigned short val) {
  // We only have 2 DAC ports.  Check input here
  // to prevent indexing outside array bounds.
  if ((dacport != 0) && (dacport != 1))
    return -1;

  // write the value out.
  // note: user must still call update_analog to drive
  // the value out physically.
  write(fd_dac[dacport], &val, 1);

  return 0;
}

// update_analog()
void update_analog(void) {
  ioctl(fd_dac[0], DAC_SIMULT_UPDATE, 0);
}
