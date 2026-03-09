## LECO and ZMQ: decoupling hardware from DAQ modules

The LECO protocol makes managing communication between the different entities in an
acquisition software very interesting. The Actor/Director/Coordinator model, once understood,
is particularly powerful, and some extensions of these concepts could be very fruitful.

I have been thinking about improving the communication flow between the different components
inside and outside PyMoDAQ. A powerful tool at the heart of PyLECO is ZMQ.
I have started using it in my own software development and it allows easy asynchronous
data distribution over a network.

A promising direction is to entirely decouple the hardware layer from the DAQ modules and
instead fully associate it with the Actor. The DAQs would be limited to the role of directors
that query or change data. One could say that this is already the case — a DAQ has to implement
specific methods to get information from the hardware. However, the coupling between the DAQ
and the hardware is currently much tighter than it needs to be.

Let me first introduce the notion of Observable and Variable.

## Observable vs Variable

Every quantity a hardware instrument exposes falls into one of two categories:

- **Observable** — something we can *measure*. Read-only from the outside. A `DAQ_Viewer`
  director is built on observables.
- **Variable** — something we can *change*. Read-write. A `DAQ_Move` director requires at
  least one variable. Every `Variable` is also an `Observable`, as we usually need to read
  it back — for example, following a stage moving to verify it reached its target position.

## Unified hardware interface

At the hardware level, all instrument interaction can thus be reduced to two operations:

- `query_data` → get an `Observable`
- `change_to` → change a `Variable`

The point of this semantic distinction is that by exposing `read`/`write` methods targeting
specific elements of the hardware, it becomes straightforward to derive a DAQ module from
an instrument driver. A reading method translates to a `DAQ_Viewer` director asking the Actor
to update a value, while a writing method gives rise to a `DAQ_Move` director.

## Three key differences from the current approach

### 1. No master/slave conflicts

In the current architecture, the master/slave distinction can lead to read/write conflicts
when multiple modules share access to hardware. In the proposed model there is exactly
**one Actor per hardware instrument**, and it is the only entity that ever touches the
hardware directly. DAQ modules connect to the Actor through the LECO protocol and send RPC
commands to make it act as they wish. Conflicts between concurrent hardware accesses
disappear by construction.

### 2. Data channel via ZMQ Proxy

Instead of routing measurement data back and forth between the Actor and the Director
through the Coordinator — which is designed for control flow, not bulk data — a dedicated
**Data Proxy** (ZMQ XPUB/XSUB) dispatches published data from the Actor to any number of
subscribers over the network. This separates two fundamentally different communication
patterns:

- **Control flow** (commands, queries, settings): small JSON payloads, bidirectional,
  through the Coordinator.
- **Data flow** (measurements, detector frames, positions): potentially large binary
  payloads, one-way broadcast, through the Data Proxy.

This separation also enables a new concept: the **Spectator** (see below).

### 3. Modularity: one Actor, many Directors simultaneously

Because the Actor is fully decoupled from any specific DAQ module, **multiple directors
can connect to the same Actor at the same time**. A scan director, a live viewer, and a
data logger can all subscribe to the same camera Actor simultaneously, each receiving
every published frame independently. No special coordination between them is required —
the ZMQ PUB/SUB pattern handles fan-out natively.

This also means that an Actor can be shared across different PyMoDAQ instances running on
different machines, or even across different software frameworks that speak LECO.

## Conceptual model

```
   ┌─ Machine A (hardware side) ──────────────────────────────────┐
   │                                                              │
   │   LECO Coordinator ◄──────────────── (links to other         │
   │         |                             Coordinators)          │
   │   Data Proxy (ZMQ XPUB/XSUB)                                 │
   │         |                                                    │
   │   PymodaqActor                                               │
   │     ├── RPC methods ──────────────► Coordinator              │
   │     └── DataPublisher ────────────► Data Proxy ──────────┐   │
   └──────────────────────────────────────────────────────────┼───┘
                                                              │
   ┌─ Machine B (client side) ────────────────────────────────┼──┐
   │                                                          │  │
   │   Director(s)          ─── RPC via Coordinator ───────►  │  │
   │   (DAQ_Move, DAQ_Viewer)                                 │  │
   │                                                          │  │
   │   Spectator(s)         ─── ZMQ SUB ◄─────────────────────┘  │
   │   (subscribe-only)                                          │
   └─────────────────────────────────────────────────────────────┘
```

## The Spectator concept

A Spectator is a lightweight subscriber that connects only to the Data Proxy.
Unlike a Director, it has no RPC channel to the Actor and cannot issue commands.
It simply subscribes to one or more Actor topics and receives every published frame.

Spectators are useful for:

- **Live monitoring**: a separate display process that shows the current state of an
  instrument without interfering with an ongoing acquisition.
- **Data logging**: a background process that records every published frame to disk,
  independently of what the Directors are doing.
- **Cross-instrument analysis**: a Spectator can subscribe to several Actors simultaneously
  and correlate their data streams in real time — for example, synchronising a position
  readout with a detector frame.

Because the ZMQ PUB/SUB pattern is purely additive — adding a new subscriber never
affects the publisher or existing subscribers — Spectators are completely transparent to
both the Actor and the Directors.
