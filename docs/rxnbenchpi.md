# rxnbenchpi

Raspberry Pi bench box for the RxnRover instrument cluster (Location: SPD138).

look at deployment.md to see how to set up the backend on the raspberry pi.

## What this is for

This Pi is meant to host SiLA2 servers wrapping lab instruments - a pH probe
and a gantry (Sovol SV08, controlled via a Moonraker client) - for the
RxnRover chemical automation project. A lab workstation acts as the SiLA2
client and discovers these servers over the network via mDNS/DNS-SD.

## Current status

Freshly brought up. Networking and SSH access are working. No
instrument-facing services are deployed yet - see "Not yet set up" below.

## Network

This Pi runs its own DHCP server (`dnsmasq`) on `eth0` for an isolated,
unmonitored instrument switch - this is **not** the wider lab network.

- Pi address: `192.168.50.1/24`
- DHCP range handed to instruments: `192.168.50.10 - 192.168.50.100`
- No gateway/internet is provided on this segment, by design.

> **Do not connect this Pi (or its switch) to the lab network while
> `dnsmasq` is running** - it will hand out conflicting DHCP leases to
> other devices. See `docs/rxnbench_info` in the `internal-docs` repo for
> the full warning and how to disable it first
> (`sudo systemctl disable --now dnsmasq`).

## Connecting

Plug into the instrument switch and the Pi's own `dnsmasq` hands your
machine a `192.168.50.0/24` lease automatically - no manual network config
needed. Then:

```bash
ssh <user>@192.168.50.1
# or, via mDNS:
ssh <user>@rxnbenchpi.local
```

Note the address is `192.168.50.1` (Pi as gateway), **not** `192.168.1.50`
- easy to transpose. Credentials live in `internal-docs` (see below).

## Services currently running

| Service | Purpose |
| --- | --- |
| `ssh` | Remote access |
| `avahi-daemon` | mDNS/DNS-SD advertising (`rxnbenchpi.local`) - the same discovery mech>
| `dnsmasq` | DHCP server for the instrument switch (see Network above) |
| `NetworkManager` | Network configuration |
| `rxnbench-gantry` | SiLA server for Gantry |
| `rxnbench-ph` | SiLA server for Gantry |

## Where to find the rest

Full setup history, credentials, and SSH key info live in the
`internal-docs` repo at `docs/rxnbench_info` - intentionally not here
