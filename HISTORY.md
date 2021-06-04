# Release History

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
