/***************************************************************************
 *
 *  cleario.c
 *
 *  This program is used to close all outputs on the PCI-DDA02-16
 *  A mix of Warren Jaspers test_dda0X-1.6.c and Curt Wuollet's smio.c
 *  Linux loadable module(pci-dda0X_16).
 *
 ***************************************************************************/

#include <stdio.h>	/* This Was Added */
#include <sys/types.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <time.h>
#include <ctype.h>
#include <math.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include "pci-dda0X-16.h"	/* Changed from dio.h */

#define FS  (65536)	/* This Was Added */

#define TRUE 1
#define MAP_ADDRESS (31*0x100000)  /* 1 mb less than total ram */
#define BYTE unsigned char
#define WORD unsigned short
#define LONG unsigned long

#define q1a   set_o(1,8) 		/* (1)  set hv1a  solenoid */
#define q1b   set_o(1,9) 		/* (2)  set hv1b  solenoid */
#define q2a   set_o(1,10)		/* (3)  set hv2a  solenoid */
#define q2b   set_o(1,11)		/* (4)  set hv2b  solenoid */
#define q3a   set_o(1,12)		/* (5)  set hv3a  solenoid */
#define q3b   set_o(1,13)		/* (6)  set hv3b  solenoid */
#define q4a   set_o(1,14)		/* (7)  set hv4a  solenoid */
#define q4b   set_o(1,15)		/* (8)  set hv4b  solenoid */
#define q5a   set_o(2,0)		/* (9)  set hv5a  solenoid */
#define q5b   set_o(2,1)		/* (10) set hv5b  solenoid */
#define q6a   set_o(2,2)		/* (11) set hv6a  solenoid */
#define q6b   set_o(2,3)		/* (12) set hv6b  solenoid */
#define q7a   set_o(2,4)		/* (13) set hv7a  solenoid */
#define q7b   set_o(2,5)		/* (14) set hv7b  solenoid */ 
#define q8a   set_o(2,6)		/* (15) set hv8a  solenoid */
#define q8b   set_o(2,7)		/* (16) set hv8b  solenoid */
#define q9a   set_o(2,8)  		/* (17) set hv9a  solenoid */
#define q9b   set_o(2,9)		/* (18) set hv9b  solenoid */ 
#define q10a  set_o(2,10)		/* (19) set hv10a solenoid */ 
#define q10b  set_o(2,11)		/* (20) set hv10b solenoid */
#define q11a  set_o(2,12)		/* (21) set hv11a solenoid */
#define q11b  set_o(2,13)		/* (22) set hv11b solenoid */
#define q12a  set_o(2,14)		/* (23)	set hv12a solenoid */
#define q12b  set_o(2,15)		/* (24) set hv12b solenoid */
#define q13a  set_o(0,0) 		/* (25) set hv13a solenoid */	
#define q13b  set_o(0,1)		/* (26) set hv13b solenoid */ 
#define q14a  set_o(0,2) 		/* (27) set hv14a solenoid */
#define q14b  set_o(0,3) 		/* (28) set hv14b solenoid */
#define q15a  set_o(0,4)		/* (29) set hv15a solenoid */ 
#define q15b  set_o(0,5) 		/* (30) set hv15b solenoid */
#define q16a  set_o(0,6) 		/* (31) set hv16a solenoid */
#define q16b  set_o(0,7) 		/* (32) set hv16b solenoid */
#define q17a  set_o(0,8) 		/* (33) set hv17a solenoid */
#define q17b  set_o(0,9) 		/* (34) set hv17b solenoid */
#define q18a  set_o(0,10) 		/* (35) set hv18a solenoid */
#define q18b  set_o(0,11) 		/* (36) set hv18b solenoid */
#define q19a  set_o(0,12) 		/* (37) set hv19a solenoid */
#define q19b  set_o(0,13) 		/* (38) set hv19b solenoid */
#define q20a  set_o(0,14)		/* (39) set hv20a solenoid */ 
#define q20b  set_o(0,15)		/* (40) set hv20b solenoid */ 		
#define q21a  set_o(1,0)		/* (41) set hv21a solenoid */
#define q21b  set_o(1,1)		/* (42) set hv21b solenoid */
#define qh1a  set_o(1,2)		/* (43) set hh1a  solenoid */
#define qh1b  set_o(1,3)		/* (44) set hh1b  solenoid */
#define qAa   set_o(1,4)		/* (45) set aira  solenoid */
#define qAb   set_o(1,5)		/* (46)	set airb  solenoid */
#define qpmp  set_o(1,6)		/* (47) set hpmp  pump solenoid */
#define qpow  set_o(1,7)		/* (48) set 3phv  mains power */


#define cq1a  clr_o (1,8) 		/* (1)  reset hv1a  solenoid */
#define cq1b  clr_o(1,9) 		/* (2)  reset hv1b  solenoid */
#define cq2a  clr_o(1,10)		/* (3)  reset hv2a  solenoid */
#define cq2b  clr_o(1,11)		/* (4)  reset hv2b  solenoid */
#define cq3a  clr_o(1,12)		/* (5)  reset hv3a  solenoid */
#define cq3b  clr_o(1,13)		/* (6)  reset hv3b  solenoid */
#define cq4a  clr_o(1,14)		/* (7)  reset hv4a  solenoid */
#define cq4b  clr_o(1,15)		/* (8)  reset hv4b  solenoid */
#define cq5a  clr_o(2,0)		/* (9)  reset hv5a  solenoid */
#define cq5b  clr_o(2,1)		/* (10) reset hv5b  solenoid */
#define cq6a  clr_o(2,2)		/* (11) reset hv6a  solenoid */
#define cq6b  clr_o(2,3)		/* (12) reset hv6b  solenoid */
#define cq7a  clr_o(2,4)		/* (13) reset hv7a  solenoid */
#define cq7b  clr_o(2,5)		/* (14) reset hv7b  solenoid */ 
#define cq8a  clr_o(2,6)		/* (15) reset hv8a  solenoid */
#define cq8b  clr_o(2,7)		/* (16) reset hv8b  solenoid */
#define cq9a  clr_o(2,8)  		/* (17) reset hv9a  solenoid */
#define cq9b  clr_o(2,9)		/* (18) reset hv9b  solenoid */ 
#define cq10a clr_o(2,10)		/* (19) reset hv10a solenoid */ 
#define cq10b clr_o(2,11)		/* (20) reset hv10b solenoid */
#define cq11a clr_o(2,12)		/* (21) reset hv11a solenoid */
#define cq11b clr_o(2,13)		/* (22) reset hv11b solenoid */
#define cq12a clr_o(2,14)		/* (23)	reset hv12a solenoid */
#define cq12b clr_o(2,15)		/* (24) reset hv12b solenoid */
#define cq13a clr_o(0,0) 		/* (25) reset hv13a solenoid */	
#define cq13b clr_o(0,1)		/* (26) reset hv13b solenoid */ 
#define cq14a clr_o(0,2) 		/* (27) reset hv14a solenoid */
#define cq14b clr_o(0,3) 		/* (28) reset hv14b solenoid */
#define cq15a clr_o(0,4)		/* (29) reset hv15a solenoid */ 
#define cq15b clr_o(0,5) 		/* (30) reset hv15b solenoid */
#define cq16a clr_o(0,6) 		/* (31) reset hv16a solenoid */
#define cq16b clr_o(0,7) 		/* (32) reset hv16b solenoid */
#define cq17a clr_o(0,8) 		/* (33) reset hv17a solenoid */
#define cq17b clr_o(0,9) 		/* (34) reset hv17b solenoid */
#define cq18a clr_o(0,10) 		/* (35) reset hv18a solenoid */
#define cq18b clr_o(0,11) 		/* (36) reset hv18b solenoid */
#define cq19a clr_o(0,12) 		/* (37) reset hv19a solenoid */
#define cq19b clr_o(0,13) 		/* (38) reset hv19b solenoid */
#define cq20a clr_o(0,14)		/* (39) reset hv20a solenoid */ 
#define cq20b clr_o(0,15)		/* (40) reset hv20b solenoid */ 		
#define cq21a clr_o(1,0)		/* (41) reset hv21a solenoid */
#define cq21b clr_o(1,1)		/* (42) reset hv21b solenoid */
#define cqh1a clr_o(1,2)		/* (43) reset hha   solenoid */
#define cqh1b clr_o(1,3)		/* (44) reset hhb   solenoid */
#define cqAa  clr_o(1,4)		/* (45) reset aira  solenoid */
#define cqAb  clr_o(1,5)		/* (46)	reset airb  solenoid */
#define cqpmp clr_o(1,6)		/* (47) reset hpmp  pump solenoid */
#define cqpow clr_o(1,7)		/* (48) reset 3phv  mains power */


char *DevName = "/dev/dda0x-16/da0_0";	/* Changed from /dev/dio48H_1A */
char DevNameIO[20];
int  Mode     = 0;
int  Status;
int  mfd;
BYTE  bReg;

int fd_0A, fd_0B, fd_0C;		/* Was fd_1A, fd_1B, fd_1C; */
int fd_1A, fd_1B, fd_1C;		/* Was fd_2A, fd_2B, fd_2C; */
unsigned short value;

//static int fd_dac[8];    // we are only going to use 2 for this test.

//int  DAC_Gain[4]  = {UP_10_0V, UP_10_0V, UP_10_0V, UP_10_0V};


typedef struct
{
    unsigned short     reg[512];
    float              alg[512];
    int		       flags;
} LMAP;

LMAP *mapp;

/* Forward Declarations */

void setup_io(void);
void close_io(void);
// void read_io(void);
void write_io(void);
void solve(void);
// int  get_i(short reg,short bit);
void set_o(short reg,short bit);
void clr_o(short reg,short bit);

int cnt = 0;
int ms = 90002;
// Scan rate of 90002 is as close as poss to original Feto404 PLC, running slightly fast

main(int argc,char *argv[])
{

    /* Let's do the nasty stuff first */
    /* We are using 1mb of ram excluded from the linux mm as shared memory */
    /* By typedef'ing our struct and mmaping it at MAP_ADDRESS we in effect */
    /* allocate it in the shared memory translated into user space. If this */
    /* seems like FM to you, don't feel bad, I had to read the kernel sources */
    /* to figure out where we actually allocate anything. hint, the compiler  */
    /* did it */

    /* Note, I should check if there is a way to get and drop perms for */
    /* /dev/mem without running as root or chmod'ing /dev/mem. I don't  */
    /* think ioperm() covers this. (security) */

    if(( mfd = open("/dev/mem",O_RDWR)) < 0)
    {
        perror("dev/mem open failed");
        exit(1);
    }
    mapp = (LMAP *) mmap( 0,sizeof(LMAP),PROT_READ | PROT_WRITE,MAP_SHARED,mfd,MAP_ADDRESS);
    if(MAP_FAILED == mmap)
    {
        perror("mmap failed");
        exit(1);
    }
    close(mfd);

    /* We should now have a shared memory map with no fuss. The code above */
    /* should be copied into all the map users. The declarations will go   */
    /* into a common header file for abstraction.                          */


// printf("usleep value in microseconds: \n");
// scanf("%d", &ms);  

    setup_io();
    mapp->flags = 0;
    
     for (cnt = 0; cnt < 2; cnt++) //&& cnt<2 )
    {
        while(mapp->flags != 0) ;
        mapp->flags = 1;
	solve();   
	printf("count: %d\n", cnt);
        write_io();
        mapp->flags = 0;
        usleep(ms);
    }


//    while( TRUE ) //&& cnt<200 )
//    {
//        while(mapp->flags != 0) ;
//        mapp->flags = 1;
//	solve();   
//	printf("count: %d\n", cnt);
//        write_io();
//        mapp->flags = 0;
//        usleep(ms);
//	cnt++;
//   }

}
void setup_io(void)
{
	/* open the dac */
	
//	 	strcpy(DevNameIO, "/dev/dda0X-16_DA0");
// 	 if ((fd_dac[0] = open(DevNameIO, O_RDWR )) < 0) {
//  	 perror("DevNameIO");
//   	 printf("error opening device %s\n", DevNameIO);
//   	 exit(2);
// 	}
// 	 ioctl(fd_dac[0], DAC_SET_GAINS, UP_10_0V);
//
//  	strcpy(DevNameIO, "/dev/dda0X-16_DA1");
//  	if ((fd_dac[1] = open(DevNameIO, O_RDWR )) < 0) {
//    perror("DevNameIO");
//    printf("error opening device %s\n", DevNameIO);
//    exit(2);
// 	 }
// 	 ioctl(fd_dac[1], DAC_SET_GAINS, UP_10_0V);
   
  /* open the dio */
     strcpy(DevNameIO, "/dev/dda0x-16/dio0_0A");
  if ((fd_0A = open(DevNameIO, O_RDWR )) < 0) {
    perror("DevNameIO");
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }
  strcpy(DevNameIO, "/dev/dda0x-16/dio0_0B");
  if ((fd_0B = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }
  strcpy(DevNameIO, "/dev/dda0x-16/dio0_0C");
  if ((fd_0C = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  strcpy(DevNameIO, "/dev/dda0x-16/dio0_1A");
  if ((fd_1A = open(DevNameIO, O_RDWR )) < 0) {
    perror("DevNameIO");
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

 strcpy(DevNameIO, "/dev/dda0x-16/dio0_1B");
  if ((fd_1B = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }

  strcpy(DevNameIO, "/dev/dda0x-16/dio0_1C");
  if ((fd_1C = open(DevNameIO, O_RDWR )) < 0) {
    perror(DevNameIO);
    printf("error opening device %s\n", DevNameIO);
    exit(2);
  }
    ioctl(fd_0A, DIO_SET_DIRECTION, 0);
    ioctl(fd_0B, DIO_SET_DIRECTION, 0);
    ioctl(fd_0C, DIO_SET_DIRECTION, 0);
    ioctl(fd_1A, DIO_SET_DIRECTION, 0);
    ioctl(fd_1B, DIO_SET_DIRECTION, 0);
    ioctl(fd_1C, DIO_SET_DIRECTION, 0);
}
void close_io(void)
{
    close(fd_0A);
    close(fd_0B);
    close(fd_0C);
    close(fd_1A);
    close(fd_1B);
    close(fd_1C);
}
void write_io(void)
{

    BYTE buf[6];
    // mapp->reg[0] = ~ mapp->reg[0]; /* toggle for testing */
    buf[0] = mapp->reg[0] &  0x00ff;
    buf[1] = mapp->reg[0] >> 8;
    buf[2] = mapp->reg[1] &  0x00ff;
    buf[3] = mapp->reg[1] >> 8;
    buf[4] = mapp->reg[2] & 0x00ff;
    buf[5] = mapp->reg[2] >> 8;
    write(fd_1A,&buf[0],1) ;
    write(fd_1B,&buf[1],1) ;
    write(fd_1C,&buf[2],1) ;
    write(fd_0A,&buf[3],1) ;
    write(fd_0B,&buf[4],1) ;
    write(fd_0C,&buf[5],1) ;
}

void solve(void)
{

/* Set All Outputs To OFF  */

if(cnt==1)  { cq1a; cq1b; }
        if(cnt==1)  { cq2a; cq2b; }
        if(cnt==1)  { cq3a; cq3b; }
        if(cnt==1)  { cq4a; cq4b; }
        if(cnt==1)  { cq5a; cq5b; }
        if(cnt==1)  { cq6a; cq6b; }
        if(cnt==1)  { cq7a; cq7b; }
        if(cnt==1)  { cq8a; cq8b; }
        if(cnt==1)  { cq9a; cq9b; }
        if(cnt==1) { cq10a; cq10b; }
        if(cnt==1) { cq11a; cq11b; }
        if(cnt==1) { cq12a; cq12b; }
        if(cnt==1) { cq13a; cq13b; }
        if(cnt==1) { cq14a; cq14b; }
        if(cnt==1)  { cq15a; cq15b; }
        if(cnt==1)  { cq16a; cq16b; }
        if(cnt==1)  { cq17a; cq17b; }
        if(cnt==1)  { cq18a; cq18b; }
        if(cnt==1)  { cq19a; cq19b; }
        if(cnt==1)  { cq20a; cq20b; }
        if(cnt==1)  { cq21a; cq21b; }
        if(cnt==1)  { cqh1a; cqh1b; }
        if(cnt==1)  { cqAa; cqAb; }
        if(cnt==1)  { cqpmp; cqpow; }
        if(cnt==2)  { cnt=0; }

}
/*
int get_i(short reg,short bit)
{
    if(mapp->reg[reg] & (0x01 << bit)) return(1);
    else return(0);
}
*/

void set_o(short reg,short bit)
{
    mapp->reg[reg] |= (0x01 << bit);
}

void clr_o(short reg,short bit)
{
    mapp->reg[reg] &= ~(0x01 << bit);
}
