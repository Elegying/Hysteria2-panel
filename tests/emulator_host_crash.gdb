# CI-only diagnosis of the Linux API 36 emulator host crash. Keep guest/app
# memory, frame arguments and local variables out of published diagnostics.
set pagination off
set confirm off
set print frame-arguments none
set print entry-values no
set print thread-events off
set debuginfod enabled off
handle SIGPIPE SIGUSR1 SIGUSR2 SIGALRM nostop noprint pass
set logging file emulator-host-stack.txt
set logging overwrite off
catch signal SIGILL SIGSEGV SIGABRT
commands
  silent
  set logging enabled on
  printf "signalNumber=%d\n", $_siginfo.si_signo
  info program
  thread apply all backtrace 12
  info sharedlibrary
  x/8i $pc
  set logging enabled off
  # Pass the signal to the original handler, including recoverable probes.
  continue
end
run
