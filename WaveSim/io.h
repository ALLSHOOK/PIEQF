/*** setup and close ***/
void close_io(void);
void setup_io(void);

/*** set/clr digital outputs ***/
int set_o(short, short);
int clr_o(short, short);

/*** set values of analog outputs ***/
// interface: first call set_analog on all dac ports you want to
// set new values for, then call update_analog to update all the
// physical voltage outputs simultaneously.
int set_analog(int dacport, unsigned short val);
void update_analog(void);
