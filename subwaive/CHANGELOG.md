# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2025-11-03

### Added

- Report for recent check-in activity (ex. volunteers and board members according to Docuseal)

## [1.0.1] - 2025-10-24

### Added

- Local group creation based on OIDC group claims
- .env file descriptions of group privileges **added** when container restarts

### Fixed

- Protect against nulls for event-less check-ins
- Changed last check-in list to be by check-in record creation date, which always exists, preventing event-less check-ins from always being top results
- Protect against missing waiver template in NFC workflow


## [1.0.0] - 2025-10-23

### Added

- Support for NFC check-in terminal

