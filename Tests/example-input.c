#include <stdio.h>




main(int argc, char *argv[]) {
  FILE *pipe;
  char msg[80];

  pipe = fopen("my_pipe", "w");

  while (1) {
    // wait for something to happen
    
    // ...

    // format a message
    sprintf(msg, "hello, Dave\n");

    // write it to the pipe
    fputs(msg, pipe);
  }
}

  
