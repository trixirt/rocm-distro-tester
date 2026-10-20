prompts/ - Self-contained XML prompt corpus for pi

Prompt files follow the fedora-pi-prompts XML convention and are
invoked from the working directory that should be acted upon:

    pi < prompts/<category>/<name>.xml

Categories
------------------------------------------------------------------------

development/
  Prompts that develop THIS project: onboarding analysis, design
  reviews, code and docs verification. See development/README.txt.

test/    (planned)
  Prompts that analyze test runs of distro packages, mirroring the
  test/ and mock/ categories in fedora-pi-prompts. These will arrive
  as the rocm-distro-containers test suite is migrated into
  pkg-tests/; each run.sh in a test directory should end with
  `pi < <prompt>` rather than a hard-coded home-directory path.
