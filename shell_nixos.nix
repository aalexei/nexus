with import <nixpkgs> {};

# Make a new "derivation" that represents our shell
stdenv.mkDerivation rec {
  name = "my-environment";

  # The packages in the `buildInputs` list will be added to the PATH in our shell
  buildInputs = [
    figlet
    python37
    python37Packages.apsw
    python37Packages.bleach
    python37Packages.beautifulsoup4
    python37Packages.pyqt5
  ];

  shellHook = ''
  figlet "Nexus"
  '';
}
