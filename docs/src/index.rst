PyMoDAQ
=======

PyMoDAQ is a free and open-source software, officially supported by the CNRS, to efficiently setup the acquisition
program of your experiment with Python.
It simplifies the interaction with detector and
actuator hardware to go straight to the data acquisition of interest. It provides:

* a graphical interface
* the synchronization of the connected instruments
* data saving
* a modular architecture to easily integrate new instruments in your setup
* ... and many more features!

.. grid:: 1 2 3 3
   :gutter: 3
   :class-container: pmd-landing-grid

   .. grid-item-card:: Get Started

      Install PyMoDAQ and run your first acquisition in a few minutes.

      +++

      .. button-ref:: quick_start
         :ref-type: ref
         :color: primary
         :outline:
         :expand:

         Quick Start

   .. grid-item-card:: User Guide

      Control modules, viewers, extensions, configuration, scripting, and the data model.

      +++

      .. button-ref:: user_guide
         :ref-type: ref
         :color: primary
         :outline:
         :expand:

         User's Guide

   .. grid-item-card:: Developer Guide

      Write an instrument plugin or extension, or contribute to PyMoDAQ's core.

      +++

      .. button-ref:: /developer
         :ref-type: doc
         :color: primary
         :outline:
         :expand:

         Developer's Guide

   .. grid-item-card:: API Reference

      The full API, generated from the source code docstrings.

      +++

      .. button-ref:: library_reference
         :ref-type: ref
         :color: primary
         :outline:
         :expand:

         API Reference

   .. grid-item-card:: About/Community

      Project info, changelogs, lab stories, and the PyMoDAQ ecosystem.

      +++

      .. button-ref:: about_community
         :ref-type: ref
         :color: primary
         :outline:
         :expand:

         About/Community

.. raw:: html

   <div style="text-align: center">
      <iframe width="672" height="378" src="https://www.youtube.com/embed/PWuZggs_HwM" title="YouTube video player"
      frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
       allowfullscreen></iframe>
   </div>


French version `here`_

.. _here: https://youtu.be/TrRy6HL3h3c

Community and training
-----------------------

PyMoDAQ is maintained by a growing community of experimental physicists, and training sessions and
gatherings of the community are organized every year.

.. figure:: /image/JT_Pymodaq_2025.png
   :alt: Pymodaq days
   :width: 500

   The 43 people attending the last PyMoDAQ days in Montpellier. See you in october 2026 for the next
   PyMoDAQ Days in Orsay!

.. note::
   * Training session in Gif sur Yvette, France, 3-7 march 2026, `CNRS Formation Entreprise`_
   * Training session in Bordeaux, France, 15-18 June 2026, Action Nationale de Formation CNRS
   * Fifth edition of the PyMoDAQ's Days: Orsay 7-9 October 2026. `Registration are open!`_

.. _CNRS Formation Entreprise: https://cnrsformation.cnrs.fr/liste-stages-mc-PyMoDAq.html

.. _Registration are open!: https://jt-pymodaq26.sciencesconf.org/index

Contact
-------

You can find video tutorials on the
`YouTube channel <https://youtube.com/playlist?list=PLGdoHByMKfIdn-N51goippSSP_9iG4wds>`_.

Do not hesitate to address your questions to the mailing list
`pymodaq@services.cnrs.fr <mailto:pymodaq@services.cnrs.fr>`_ or
`sebastien.weber@cemes.fr <mailto:sebastien.weber@cemes.fr>`_.

For detailed information about the code and the features of PyMoDAQ, please visit the
`GitHub repository <https://github.com/pymodaq/pymodaq>`_. Do not hesitate to
`submit an issue <https://github.com/pymodaq/pymodaq/issues>`_.

If you would like to get updated with the evolutions of the project, please subscribe to the
`mailing list <https://listes.services.cnrs.fr/wws/info/pymodaq>`_.

.. toctree::
   :maxdepth: 1
   :caption: Get Started
   :hidden:

   quick_start

.. toctree::
   :maxdepth: 2
   :caption: User Guide
   :hidden:

   user

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide
   :hidden:

   developer

.. toctree::
   :maxdepth: 1
   :caption: API Reference
   :hidden:

   api/api_doc

.. toctree::
   :maxdepth: 1
   :caption: About/Community
   :hidden:

   about_community
