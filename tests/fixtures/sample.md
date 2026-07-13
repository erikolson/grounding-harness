# Deployment Guide

This guide covers how the service is deployed and rolled back.

## Setup

The service reads its configuration from the environment at startup.

Install the dependencies before running anything else, or startup will fail with
a missing module error.

### Credentials

Credentials are read from the secret store and never written to disk.

## Rollback

A rollback restores the previous release and replays the migration in reverse.

Here is a heading that is not a heading, because it lives inside a fence:

```bash
# This is a shell comment, not a markdown heading.
./deploy.sh --rollback
```

The rollback script exits non-zero if the previous release cannot be found.

## Notes

### Example

The first example section describes the happy path deployment.

### Example

The second example section describes a failed deployment and its recovery.
