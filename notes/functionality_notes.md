# Automated liquid handler work notes

Date: April 28
Name: John Brittain

Both the SOVOL and Bambu lab printers have arrived today, the Bambu Lab was set up in the lab but the SOVOL remains in the box
until the Rasberry Pi / Filament come in. I hope to set the SOVOl up later when I start experimenting and playing around
with the printer.

I spoke with Lun while I was there, turns out they have selected and found a decent circuit for the PH probe and also a soil-pH probe
which will be thin enough to fit inside the well. They are kinda back-tracking on the liquid-handler part right now, but just to prove
the system works they want the pH probe at least working within the system. Though to be honest, I think that should be quite trivial,
if it's just the pH. I want to continue the design expecting both the liquid-handler and the pH probe.

I'm thinking mounting the probe adjacent to the liquid handler such that the system can swap in between.

Rail =======<--mount-->=====================       
                 |
            _____|______
            |          |
            |          |
            |          |
        pipette tip   probe

<------Platform moves to either tip-------->

               |      |
               |      |
               | vial |
               |      |
               --------

Nevermind, not sure if this could possible work given the space between vials, so whenever you dip the pipette into a vial
the pH probe would either have to (have enough clearence not to tough other vials or fit inside an adjacent vial), this
I mean could actually be benficial if #1 ensured that both the probe and the pipette could simotenously fit two adjacent vials,
and come up with a useful scenario where reading the pH of a soluton and pipetting another would make sense.

Maybe, by devising a mechnanism which can physically move, or rotate the tool out of the way would be useful. I'm envisioning some sort of
dual-sided rotational mounting system, where you mount the probe on one side, pipete on another, these are connected by some sort of central axel
which can be rotated depending on which tool you'd like to use. Either having them physically connected (in which case you could only use one tool),
or independent of eachother (more complex, but allows parallel use). 

Lun did mention that any sort of part, or mounting plate could possibly be manfuactured at the machine shop, but we also have a 3D-printer for this purpose.

Anyways in summary:

- Email the creators of the reference article to get 3D models of pipette system / mounting plates
- Figure out mounting plate scenario (everything should try to fit normal lab-standards as much as possible)
- FIgure out a dual-head mounting system
- Gather datasheets / material on the new pH probe we are ordering