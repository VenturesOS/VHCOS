import { useState, useEffect } from 'react';
import { candidateAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { toast } from 'sonner';
import { Search, UserCircle, Mail, Phone, FileText } from 'lucide-react';

export default function RecruiterCandidatesPage() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadCandidates();
  }, []);

  const loadCandidates = async () => {
    try {
      const res = await candidateAPI.getAll();
      setCandidates(res.data);
    } catch (error) {
      toast.error('Failed to load candidates');
    } finally {
      setLoading(false);
    }
  };

  const filteredCandidates = candidates.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.email.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="recruiter-candidates-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Candidates</h1>
          <p className="text-slate-500 mt-1">Browse all registered candidates</p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search candidates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredCandidates.map((candidate) => (
          <Card key={candidate.id} className="border-slate-200 hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-full bg-[#DCFCE7] flex items-center justify-center shrink-0">
                  <span className="text-[#7CB342] font-bold text-xl">
                    {candidate.name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-slate-900 truncate">{candidate.name}</h3>
                  <p className="text-sm text-slate-500 truncate">{candidate.headline || 'No headline'}</p>
                </div>
              </div>
              <div className="mt-4 space-y-2 text-sm">
                <p className="flex items-center gap-2 text-slate-600">
                  <Mail className="w-4 h-4 text-slate-400" />
                  <span className="truncate">{candidate.email}</span>
                </p>
                {candidate.phone && (
                  <p className="flex items-center gap-2 text-slate-600">
                    <Phone className="w-4 h-4 text-slate-400" />
                    {candidate.phone}
                  </p>
                )}
              </div>
              {candidate.skills?.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1">
                  {candidate.skills.slice(0, 3).map((skill) => (
                    <span
                      key={skill}
                      className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full"
                    >
                      {skill}
                    </span>
                  ))}
                  {candidate.skills.length > 3 && (
                    <span className="text-xs text-slate-400">+{candidate.skills.length - 3}</span>
                  )}
                </div>
              )}
              {candidate.resume_url && (
                <a
                  href={candidate.resume_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1 text-sm text-[#7CB342] hover:underline"
                >
                  <FileText className="w-4 h-4" /> View Resume
                </a>
              )}
            </CardContent>
          </Card>
        ))}
        {filteredCandidates.length === 0 && (
          <div className="col-span-full empty-state">
            <UserCircle className="empty-state-icon" />
            <p className="empty-state-title">No candidates found</p>
            <p className="empty-state-text">Candidates will appear here</p>
          </div>
        )}
      </div>
    </div>
  );
}
