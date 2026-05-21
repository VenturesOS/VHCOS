// Role-based navigation visibility
// Reads vhc-view from localStorage and hides menu items accordingly
// Employer mode: hide items with data-role-hide="employer"
// Candidate mode: hide items with data-role-hide="candidate"
(function(){
  var v = localStorage.getItem('vhc-view') || 'employers';
  var hide = v === 'employers' ? 'employer' : 'candidate';
  document.querySelectorAll('[data-role-hide="' + hide + '"]').forEach(function(el) {
    el.style.display = 'none';
  });
})();
