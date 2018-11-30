# sebak-monitor

------------------------

### Installation

* python: 3.6 or higher

### Deployment

1. Add slack incomming webhook url in conf.ini
2. Run

```
$ python sebak-monitor.py conf.ini
```

### Q & A

1. When you want to change checking nodes interval?
   Set [INTERVAL] CheckingBlock field in conf.ini
1. When you want to alarm with email?
   Modify `email_out` method in sebak-monitor.py

These configuration is going to change to `INI`
