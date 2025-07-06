from flask import Blueprint
from .core import financial_core
from .tuition import financial_tuition  
from .contracts import financial_contracts
from .aid import financial_aid
from .documents import financial_documents
from .divisions import financial_divisions

# Create the main financial blueprint
financial = Blueprint('financial', __name__)

# Register sub-blueprints
financial.register_blueprint(financial_core)
financial.register_blueprint(financial_tuition)
financial.register_blueprint(financial_contracts)
financial.register_blueprint(financial_aid)
financial.register_blueprint(financial_documents)
financial.register_blueprint(financial_divisions)

# Import routes from sub-modules for backward compatibility
from .core import *
from .tuition import *
from .contracts import *
from .aid import *
from .documents import *
from .divisions import * 