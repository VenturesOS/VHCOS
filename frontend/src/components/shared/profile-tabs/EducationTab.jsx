import { GraduationCap } from 'lucide-react';

export default function EducationTab({ candidate }) {
  return (
    <div className="space-y-4">
      <h3 className="font-semibold text-lg">Education</h3>
      {candidate.ug_course && (
        <div className="p-4 bg-slate-50 rounded-lg border-l-4 border-blue-500">
          <div className="flex items-center gap-2 mb-1">
            <GraduationCap className="w-4 h-4 text-blue-600" />
            <span className="font-semibold text-slate-900">Undergraduate Course</span>
          </div>
          <p className="text-sm text-slate-600">{candidate.ug_course}</p>
        </div>
      )}
      {candidate.education?.length > 0 ? (
        <div className="space-y-3">
          {candidate.education.map((edu, i) => (
            <div key={`edu-${edu.degree}-${i}`} className="p-4 bg-slate-50 rounded-lg border-l-4 border-blue-500">
              <p className="font-semibold text-slate-900">{edu.degree || 'Degree'}</p>
              {edu.specialization && <p className="text-sm text-slate-500">{edu.specialization}</p>}
              <p className="text-sm text-slate-600">{edu.institution || edu.university || edu.school || ''}</p>
              {(edu.year || edu.pass_out_year) && <p className="text-xs text-slate-400 mt-1">{edu.year || edu.pass_out_year}</p>}
            </div>
          ))}
        </div>
      ) : !candidate.ug_course && (
        <p className="text-slate-500 text-center py-8">No education data available</p>
      )}
    </div>
  );
}
