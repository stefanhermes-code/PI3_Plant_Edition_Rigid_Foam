"""Single source of truth for the app version shown in the navigation bar.

Convention: bump this on every commit that gets pushed to GitHub.
- Patch (x.y.Z) for fixes, small tweaks, content/data changes.
- Minor (x.Y.0) for new features/pages/schema additions.
- Major (X.0.0) reserved for breaking changes to the data model or workflow.

PI3 Rigid Foam Edition - forked from PI3 Plant Edition (flexible slabstock
foam) v2.0.1 on 2026-08-05. Starts its own version history from 0.1.0;
see PI3_Rigid_Foam_Edition_Change_Impact_Assessment.docx for what carries
over unchanged vs. what needs rework for rigid foam manufacturing.
"""

APP_VERSION = "0.1.0"
