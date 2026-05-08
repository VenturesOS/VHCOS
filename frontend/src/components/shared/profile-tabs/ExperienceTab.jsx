export default function ExperienceTab({ candidate }) {
  return (
    <div className="space-y-4">
      <h3 className="font-semibold text-lg">Work Experience</h3>
      {candidate.experience?.length > 0 ? (
        <div className="space-y-3">
          {candidate.experience.map((exp, i) => (
            <div key={`exp-${exp.company}-${i}`} className="p-4 bg-slate-50 rounded-lg border-l-4 border-[#7CB342]">
              <p className="font-semibold text-slate-900">{exp.designation || exp.title || 'Position'}</p>
              <p className="text-sm text-slate-600">{exp.company || 'Company'}</p>
              <p className="text-xs text-slate-400 mt-1">
                {exp.from_date && exp.to_date ? `${exp.from_date} – ${exp.to_date}` : exp.duration || ''}
              </p>
              {(exp.location || exp.department) && (
                <p className="text-xs text-slate-400">{[exp.location, exp.department].filter(Boolean).join(' · ')}</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-slate-500 text-center py-8">No experience data available</p>
      )}
    </div>
  );
}
