import { useState, useEffect } from 'react';
import { matchingAPI, applicationAPI } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import { Sparkles, Briefcase, MapPin, Star, Send, RefreshCw } from 'lucide-react';

export default function MatchingJobsPage() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null);
  const [coverLetter, setCoverLetter] = useState('');
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    loadMatches();
  }, []);

  const loadMatches = async () => {
    setLoading(true);
    try {
      const res = await matchingAPI.getJobsForCandidate();
      setMatches(res.data);
    } catch (error) {
      toast.error('Failed to load matching jobs');
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!selectedJob) return;
    setApplying(true);
    try {
      await applicationAPI.create({
        job_id: selectedJob.job_id,
        cover_letter: coverLetter,
      });
      toast.success('Application submitted!');
      setSelectedJob(null);
      setCoverLetter('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to apply');
    } finally {
      setApplying(false);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 60) return 'text-[#7CB342] bg-[#DCFCE7] border-[#7CB342]/30';
    if (score >= 40) return 'text-amber-600 bg-amber-50 border-amber-200';
    return 'text-slate-500 bg-slate-100 border-slate-200';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="matching-jobs-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold text-slate-900">Jobs For You</h1>
          <p className="text-slate-500 mt-1">AI-matched jobs based on your profile</p>
        </div>
        <Button
          variant="outline"
          onClick={loadMatches}
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh Matches
        </Button>
      </div>

      {matches.length === 0 ? (
        <Card className="border-slate-200">
          <CardContent className="p-12 text-center">
            <Sparkles className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="font-heading text-xl font-semibold text-slate-700 mb-2">No Matching Jobs Yet</h3>
            <p className="text-slate-500 max-w-md mx-auto">
              Complete your profile and upload your resume to get AI-powered job recommendations.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {matches.map((match) => (
            <Card
              key={match.job_id}
              className="border-slate-200 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => setSelectedJob(match)}
            >
              <CardContent className="p-6">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 rounded-xl bg-[#DCFCE7] flex items-center justify-center shrink-0">
                      <Briefcase className="w-7 h-7 text-[#7CB342]" />
                    </div>
                    <div>
                      <h3 className="font-heading font-semibold text-lg text-slate-900">
                        {match.job_title}
                      </h3>
                      <p className="text-slate-500">{match.company_name || 'Company'}</p>
                      <div className="flex items-center gap-2 mt-1 text-sm text-slate-500">
                        <MapPin className="w-4 h-4" />
                        {match.location}
                      </div>
                    </div>
                  </div>
                  
                  <div className={`px-4 py-2 rounded-lg border font-bold text-lg ${getScoreColor(match.score)}`}>
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4" />
                      {match.score}% Match
                    </div>
                  </div>
                </div>

                <div className="mt-4">
                  <p className="text-sm text-slate-600">{match.explanation}</p>
                </div>

                {match.matched_skills?.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-1">
                    {match.matched_skills.map((skill) => (
                      <span
                        key={skill}
                        className="px-2 py-1 bg-[#DCFCE7] text-[#7CB342] text-xs rounded-full"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-4 flex justify-end">
                  <Button
                    className="bg-[#7CB342] hover:bg-[#689F38]"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedJob(match);
                    }}
                  >
                    Apply Now
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Apply Dialog */}
      <Dialog open={!!selectedJob} onOpenChange={() => setSelectedJob(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Apply to {selectedJob?.job_title}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="bg-slate-50 p-4 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-slate-900">{selectedJob?.job_title}</p>
                  <p className="text-sm text-slate-500">{selectedJob?.company_name}</p>
                </div>
                <div className={`px-3 py-1 rounded-lg font-semibold ${getScoreColor(selectedJob?.score || 0)}`}>
                  {selectedJob?.score}% Match
                </div>
              </div>
            </div>
            
            <div className="bg-[#DCFCE7]/30 p-3 rounded-lg">
              <p className="text-sm text-[#7CB342]">
                <Sparkles className="w-4 h-4 inline mr-1" />
                {selectedJob?.explanation}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Cover Letter (Optional)</label>
              <Textarea
                value={coverLetter}
                onChange={(e) => setCoverLetter(e.target.value)}
                placeholder="Tell the employer why you're interested..."
                rows={5}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedJob(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleApply}
              disabled={applying}
              className="bg-[#7CB342] hover:bg-[#689F38]"
            >
              {applying ? (
                <div className="spinner w-4 h-4 border-2 border-white border-t-transparent mr-2" />
              ) : (
                <Send className="w-4 h-4 mr-2" />
              )}
              Submit Application
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
