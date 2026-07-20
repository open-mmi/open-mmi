# Project philosophy

`open-mmi` exists to make vehicle integration knowledge reusable.

Too much CAN-bus reverse-engineering is rediscovered privately, lost in forum threads, or locked inside one-off products. `open-mmi` aims to provide a shared Linux-based layer where vehicle profiles, decoded states, and dashboard/action integrations can be maintained openly.

## Goals

- keep vehicle integration local-first
- keep vehicle profiles reusable
- translate every vehicle into one shared canonical event and status vocabulary
- keep the core daemon small and boring
- keep vehicle-specific CAN knowledge out of core Python
- make it possible to add vehicle support without reinventing the whole project
- provide useful status/state output for multiple UI consumers
- support right-to-repair and owner-controlled vehicle integration

## Non-goals

`open-mmi` is not intended to become:

- a locked commercial head unit
- a proprietary vehicle-profile marketplace
- a cloud-required vehicle service
- a paywalled CAN database
- a safety-critical replacement for OEM warnings or diagnostics
- a drivetrain/body-control project

## Community model

The project should allow different levels of contribution:

- documentation fixes
- install notes
- screenshots and example output
- CAN captures
- vehicle decode notes
- vehicle profiles
- action modules
- dashboard/UI consumers
- tests and tooling

A contributor should not need to understand the whole daemon to help with one vehicle, one status mapping, or one UI consumer.

## Core and edges

The core should be conservative.

The edges should be flexible.

```text
core daemon:
  small
  stable
  passive-first
  profile-driven
  boring

vehicle profiles:
  reusable
  reviewable
  manufacturer-specific at the CAN boundary
  canonical at the event/status boundary
  marked experimental/stable
  kept out of core Python

UI/actions:
  flexible
  user-controlled
  replaceable
  built on decoded state, not raw CAN
