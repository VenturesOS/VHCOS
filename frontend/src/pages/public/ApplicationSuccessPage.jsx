import { Link } from 'react-router-dom';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { CheckCircle2, ArrowRight } from 'lucide-react';

export default function ApplicationSuccessPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4" data-testid="application-success-page">
      <Card className="max-w-lg w-full">
        <CardContent className="p-8 text-center">
          {/* Success Icon */}
          <div className="mb-6">
            <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto">
              <CheckCircle2 className="h-10 w-10 text-green-600" />
            </div>
          </div>

          {/* Primary Heading - ALL CAPS, BOLD */}
          <h1 
            className="text-2xl md:text-3xl font-bold text-gray-900 mb-4 uppercase tracking-wide"
            data-testid="success-heading"
          >
            THANK YOU FOR YOUR APPLICATION
          </h1>

          {/* Subheading - lowercase/sentence case, ITALIC */}
          <p 
            className="text-lg text-gray-600 italic mb-8"
            data-testid="success-subheading"
          >
            Our recruiters will review your application and get in touch with you
          </p>

          {/* Divider */}
          <div className="border-t border-gray-200 my-8"></div>

          {/* Additional info */}
          <p className="text-sm text-gray-500 mb-6">
            We appreciate your interest in joining our talent network. 
            You will receive updates about your application status via email.
          </p>

          {/* View More Jobs Button */}
          <Link to="/careers">
            <Button size="lg" className="w-full md:w-auto" data-testid="view-more-jobs-btn">
              View more jobs
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </Link>
        </CardContent>
      </Card>

      {/* Footer */}
      <div className="absolute bottom-4 text-center text-gray-400 text-sm">
        <p>© {new Date().getFullYear()} Ventures HRD</p>
      </div>
    </div>
  );
}
