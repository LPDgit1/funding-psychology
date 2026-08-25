// The bundled Windows runtime can report ENOMEM from os.userInfo() under the
// desktop sandbox.  tsx only needs a stable temporary-directory suffix.
if (typeof process.geteuid !== "function") process.geteuid = () => 0;
