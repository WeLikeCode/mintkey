// Force @tiptap/core and @tiptap/pm to 2.27.2 to fix version mismatch
// in adminjs's tiptap dependency tree (extensions@2.27.x require core@^2.7.0
// but adminjs peers pin core@2.1.x).
function readPackage(pkg) {
  if (pkg.dependencies && pkg.dependencies['@tiptap/core']) {
    pkg.dependencies['@tiptap/core'] = '2.27.2';
  }
  if (pkg.peerDependencies && pkg.peerDependencies['@tiptap/core']) {
    pkg.peerDependencies['@tiptap/core'] = '2.27.2';
  }
  if (pkg.dependencies && pkg.dependencies['@tiptap/pm']) {
    pkg.dependencies['@tiptap/pm'] = '2.27.2';
  }
  if (pkg.peerDependencies && pkg.peerDependencies['@tiptap/pm']) {
    pkg.peerDependencies['@tiptap/pm'] = '2.27.2';
  }
  return pkg;
}

module.exports = { hooks: { readPackage } };
