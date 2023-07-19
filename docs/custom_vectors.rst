====================================
Generating Vectors for your own Chip
====================================

In order to generate vectors for a chip that is not yet natively supported in
*dumpling*, you will have leverage the dumpling library in your own chip
specific vector generation script. Understanding the
basic structure of the *dumpling* library is a very important preliminary to
start developing your own custom script. If you did not already went through the
:ref:`Architecture <architecture>` chapter, make sure to go through the
documentation to understand how the different classes of *dumpling* interact
with each other.

That being said, the already existing scripts, e.g. the one for the *Siracusa*
SoC should provide a good starting point for your own chip. 


