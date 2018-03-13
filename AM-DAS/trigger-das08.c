/* code to trigger vertical motion of shake table for PIEQF by Andy Michael */
/* using this code to sample some number of channels, perform an STA/LTA calculation, and then print out a message to either start the shake table pump, or trigger the shake table */
/* input file format: */
/* line 1: number of samples to try for in a second, may be that somewhat fewer will actually be taken */
/* line 2: minimum time between turning on the pump */
/* line 2-n: device-name-of-channel number-of-samples-for-short-term-average number-of-samples-for-long-term-average STA/LTA-threshold-to-turn-pumps-on STA/LTA-threshold-to-trigger-action minimum-time-between-trigger-actions-in-seconds */
/* input file is read from standard input */

/*
 * Copyright (C) 2007  Warren Jasper
 * All rights reserved.
 *
 */


/***************************************************************************
 *
 *  test-das08.c
 *
 *  This program is used to test the PCI-DAS08 Analog to Digital
 *  Linux loadable module.
 *
 ***************************************************************************/

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <sys/types.h>
#include <sys/ioctl.h>

#include "pci-das08.h"



/***************************************************************************
 *
 *  Global Data
 *
 ***************************************************************************/

#define MAXSAMPLES 1000
#define MAXCHANNELS 8

useconds_t btwsamples = 40000;

typedef struct a2dchannel {
	char DevName[100]; /* name of the channel on card */
	int stlength; /* the number of samples to use in the short term sum */
	int ltlength; /* the number of samples to use in the long term sum */
	float ratiolength; /* ltlength divided by stlength */
	float onthresh; /* the STA/LTA threshold to turn the pump on */
	float trigthresh; /* the STA/LTA threshold to trigger the action */
	int secbtwtriggers; /* the minimum time in seconds between triggers for this channel */
	int sampsbtwtriggers; /* the minimum time in samples between triggers for this channel */
	int samples[MAXSAMPLES]; /* an array of samples */
	int meanvalue; /* a mean value obtained during startup to account for DC offsets */
	int stsum; /* the short term sum */
	int ltsum; /* the long term sum */
	int index; /* where in the array are we */
} tempchannel;

struct a2dchannel channel[MAXCHANNELS];

int secondspump; /* seconds between starting up the pump */
int samplespersecond; /* samples per second  to try for */
int nchan; /* number of channels we are trying to sample */

int fdADC;                   /* A/D file descriptors */

/* code from the driver */

/* Programmable Range and Gain Settings */
#define BP_10_00V  (0x00 << 8)    /* +/- 10V      */
#define BP_5_00V   (0x01 << 8)    /* +/-  5V      */
#define BP_2_50V   (0x02 << 8)    /* +/-  2.5V    */
#define BP_1_25V   (0x03 << 8)    /* +/-  1.25V   */
#define UP_10_00V  (0x08 << 8)    /* 0 - 10V      */
#define UP_5_00V   (0x09 << 8)    /* 0 - 5V       */
#define UP_2_50V   (0x0a << 8)    /* 0 - 2.5V     */
#define UP_1_25V   (0x0b << 8)    /* 0 - 1.25V    */


void DoOpenDevices(DevName)
char *DevName;
{
  char str[80];

  if (( fdADC = open(DevName, ADC_SOFT_TRIGGER)) < 0 ) {
    perror(str);
    printf("error opening device %s\n", DevName);
    exit(2);
  }
}

float volts( int gain, unsigned short value )
{
  float volt;
  
  switch( gain ) {
    case BP_10_00V:
      volt = (20.0/4096.)*(value - 2048);
      break;
    case BP_5_00V:
      volt = (10.0/4096.)*(value - 2048);
      break;
    case UP_10_00V:
      volt = (10.0/4096.)*value;
      break;
    case UP_5_00V:
      volt = (5.0/4096.)*value;
      break;
  }
  return volt;
}

/* end of code from the driver */


/* main program */

main()
{
	char line[300];
	int i,j;
	/* read in the input file */
	fgets(line,300,stdin);
	sscanf(line,"%d",&samplespersecond);
	btwsamples = 1000000/samplespersecond;
	fgets(line,300,stdin);
	sscanf(line,"%d",&secondspump);
	nchan=0;
	unsigned short value;
	int cvalue;
	float ratio;
	int bytesRead;
	int Count = 1; /* read one sample at a time */


	/* read the input file */
	while (fgets(line,300,stdin)!=NULL){
		sscanf(line,"%s %d %d %f %f %d",&channel[nchan].DevName,&channel[nchan].stlength,&channel[nchan].ltlength,&channel[nchan].onthresh,&channel[nchan].trigthresh,&channel[nchan].secbtwtriggers);
		/* make sure we won't go over MAXSAMPLES */
		if(channel[nchan].ltlength>MAXSAMPLES)channel[nchan].ltlength=MAXSAMPLES;
		if(channel[nchan].stlength>MAXSAMPLES)channel[nchan].stlength=MAXSAMPLES;
		channel[nchan].ratiolength = channel[nchan].ltlength/channel[nchan].stlength;
		++nchan;
	}

	/* fill the arrays for initialization and compute the meanvalue for DC offsets and remove it from the samples and convert to absolute values */
	for(i=0;i<MAXSAMPLES;++i){
		for(j=0;j<nchan;++j){
  		DoOpenDevices(channel[j].DevName);
    	bytesRead = read(fdADC, &value, Count);
			channel[j].samples[i]=value;
  		close(fdADC);
		}
		usleep(btwsamples);
	}
	for(j=0;j<nchan;++j){
		channel[j].meanvalue=0;
		for(i=0;i<MAXSAMPLES;++i)channel[j].meanvalue+=channel[j].samples[i];
		channel[j].meanvalue/=MAXSAMPLES;
		for(i=0;i<MAXSAMPLES;++i)channel[j].samples[i]= abs(channel[j].samples[i]-channel[j].meanvalue);
	}

	/* figure out where we are in the array of samples to start */
	for(j=0;j<nchan;++j)channel[j].index=channel[j].ltlength -1;

	/* compute the initial stsum and ltsums */
	for(j=0;j<nchan;++j){
		channel[j].ltsum=0;
		for(i=0;i<channel[j].ltlength;++i)channel[j].ltsum+=channel[j].samples[i];
		channel[j].stsum=0;
		for(i=channel[j].ltlength - channel[j].stlength ;i<channel[j].ltlength;++i)channel[j].stsum+=channel[j].samples[i];
	}

	printf("Initialization Done\n");
	for(j=0;j<nchan;++j){
		printf("Channel %s meanvalue is %d\n",channel[j].DevName,channel[j].meanvalue);
	}

	/* start the infinite sampling loop and print out when trigger thresholds are exceeded */
	while(1){ /* loop forever */
		/* get some samples */
		for(j=0;j<nchan;++j){
  		DoOpenDevices(channel[j].DevName);
    	bytesRead = read(fdADC, &value, Count);
  		close(fdADC);
			/* convert the value with meanvalue and absolute value */
			cvalue = value;
			cvalue = abs(cvalue-channel[j].meanvalue);
			/* figure out where in the array we are now */
			channel[j].index=(channel[j].index+1)%(channel[j].ltlength);
			i=channel[j].index;
			/* remove the oldest sample from the ltsum */
			channel[j].ltsum-=channel[j].samples[i];
			/* put the value into the samples */
			channel[j].samples[i]=cvalue;
			/* add the new sample into the ltsum */
			channel[j].ltsum+=channel[j].samples[i];
			/* remove the oldest value from the stsum */
			i=(channel[j].index-channel[j].stlength)%channel[j].ltlength;
			channel[j].ltsum-=channel[j].samples[i];
			/* add the new sample into the stsum */
			channel[j].stsum+=channel[j].samples[i];

			/* compute the stavg/ltavg */
			ratio= (channel[j].stsum/channel[j].ltsum)*channel[j].ratiolength;

			/* do the comparisons */
			if(ratio>channel[j].onthresh)printf("%s ratio is %f exceeds %f turn on pump.\n",channel[j].DevName,ratio,channel[j].onthresh);
			if(ratio>channel[j].trigthresh)printf("%s ratio is %f exceeds %f turn on table.\n",channel[j].DevName,ratio,channel[j].trigthresh);

		}
		usleep(btwsamples);
	}
	


  return(1);
}
