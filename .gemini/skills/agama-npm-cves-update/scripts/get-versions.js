const fs = require('fs');

if (process.argv.length < 3) {
  console.error("Usage: node get-versions.js <pkg1> <pkg2> ...");
  process.exit(1);
}

const lock = JSON.parse(fs.readFileSync('package-lock.json', 'utf8'));
const pkgs = process.argv.slice(2);

pkgs.forEach(pkg => {
  const versions = [];
  for (const key in lock.packages) {
    if (key === 'node_modules/' + pkg || key.endsWith('node_modules/' + pkg)) {
      versions.push(lock.packages[key].version);
    }
  }
  
  if (versions.length === 0) {
    console.log(pkg + ': not found');
  } else {
    const uniqueVersions = [...new Set(versions)].sort();
    console.log(pkg + ': ' + uniqueVersions.join(', '));
  }
});
