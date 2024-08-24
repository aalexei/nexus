with import <nixpkgs> {};

# Make a new "derivation" that represents our shell
stdenv.mkDerivation rec {
  name = "my-environment";

  # The packages in the `buildInputs` list will be added to the PATH in our shell
  buildInputs = [
    figlet
    python3
    python3Packages.apsw
    python3Packages.bleach
    python3Packages.beautifulsoup4
    python3Packages.pyqt6
  ];

  shellHook = ''
  figlet "Nexus"
  '';
}
