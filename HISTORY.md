# Release History

## 0.1.2

### Fixes

- Make sure an argument exists in ffmpeg.args before attempting to use ffmpeg.auto on it. It's needed to be able to
  safely put in the argument in the correct position of the args list.

### Improvements

- Create new Logger class which inherits logging.Logger class for improved functionality. Merges the setup_log code,
  and a new log function `exit()` for logging a critical record and then halting code execution.
- Allow any parameter to be used with `ffmpeg.auto`.
- Allow any parameter to use both codec and/or resolution based value automation methods.

## 0.1.1

### Fixes

- Assume video resolution in a 16:9 matted canvas if it isn't 16:9 or 4:3. This is for a more accurate resolution 
  check in the ffmpeg.auto config. See the commit `3e7a979` description for more information.

### Improvements

- Use dunamai and poetry-dynamic-versioning to automatically handle versions based on git tags.
- Create a HISTORY.md file, listing changes between versions.
- Remove unused DAR and SAR calculations. Unneeded thanks to FFMPEG being awesome.

### Very minor changes

- Moved around the config a bit to separate metadata args from the rest.

## 0.1.0

- Initial Release
